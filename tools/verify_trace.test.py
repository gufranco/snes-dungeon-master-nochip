import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "tools" / "verify_trace.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify = load_module("verify_trace", MODULE_PATH)
dsp2 = verify.dsp2
dt = load_module("dsptrace", ROOT / "dsptrace.py")


def record(kind, byte):
    return (
        struct.pack("<II", 0, 0x048000)
        + struct.pack("<HH", 0, 0)
        + bytes([kind, byte])
        + bytes(8)
        + bytes([0x00, 0x30])
        + bytes([0xA9, 0x00, 0x00, 0x00])
    )


def trace_bytes(*sequences):
    chip = dsp2.Chip()
    blob = b""
    for writes in sequences:
        for value in writes:
            chip.write(value)
            blob += record(dt.KIND_WRITE, value)
        while chip.pending_output:
            blob += record(dt.KIND_READ, chip.read())
    return blob


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.bin"
        self.addCleanup(self.tmp.cleanup)

    def test_a_faithful_trace_reports_no_mismatch(self):
        self.path.write_bytes(trace_bytes([0x09, 0x10, 0x00, 0x03, 0x00], [0x01, *range(32)]))

        result = verify.check(self.path)

        self.assertEqual(result.mismatches, 0)
        self.assertGreater(result.reads, 0)
        self.assertTrue(result.ok)

    def test_a_single_altered_output_byte_is_caught(self):
        blob = bytearray(trace_bytes([0x09, 0x10, 0x00, 0x03, 0x00]))
        blob[-28 + 13] ^= 0xFF
        self.path.write_bytes(bytes(blob))

        result = verify.check(self.path)

        self.assertEqual(result.mismatches, 1)
        self.assertFalse(result.ok)

    def test_the_first_few_mismatches_are_reported_with_context(self):
        blob = bytearray(trace_bytes([0x09, 0x10, 0x00, 0x03, 0x00]))
        blob[-28 + 13] ^= 0xFF
        self.path.write_bytes(bytes(blob))

        result = verify.check(self.path)

        self.assertTrue(result.examples)
        self.assertEqual(len(result.examples[0]), 4)

    def test_a_trace_with_no_reads_is_still_counted(self):
        self.path.write_bytes(trace_bytes([0x0F]))

        result = verify.check(self.path)

        self.assertEqual(result.reads, 0)
        self.assertEqual(result.writes, 1)

    def test_state_carries_between_transactions(self):
        self.path.write_bytes(trace_bytes([0x03, 0x0F], [0x05, 1, 0x12, 0xFF]))

        result = verify.check(self.path)

        self.assertEqual(result.mismatches, 0)

    def test_a_missing_trace_is_reported_rather_than_raising(self):
        result = verify.check(Path(self.tmp.name) / "absent.bin")

        self.assertIsNone(result)


class MainTest(unittest.TestCase):
    def test_no_trace_at_all_is_a_skip_rather_than_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = verify.main(["verify_trace.py", str(Path(tmp) / "nothing.bin")])

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
