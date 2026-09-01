import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "tools" / "verify_trace.py"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify = load_module("verify_trace", MODULE_PATH)
dt = load_module("dsptrace", ROOT / "dsptrace.py")


class Puppet:
    """A part that answers what it was told to answer.

    The real check runs the cartridge's trace against the cartridge's own
    microcode, which belongs to whoever made the part and is on nobody's build
    machine. That check is a script, not a test. What the tests here pin is the
    replaying: that a write goes to the part, that a read is compared, and that a
    disagreement is counted and reported rather than passed over.
    """

    def __init__(self, answers: Any = ()) -> None:
        self.answers = list(answers)
        self.written: list[Any] = []

    def write(self, value: Any) -> None:
        self.written.append(value)

    def read(self) -> Any:
        return self.answers.pop(0) if self.answers else 0x00


def puppets(answers: Any = ()) -> Any:
    def build() -> Any:
        return Puppet(answers)

    return build


def record(kind: Any, byte: Any) -> Any:
    return (
        struct.pack("<II", 0, 0x048000)
        + struct.pack("<HH", 0, 0)
        + bytes([kind, byte])
        + bytes(8)
        + bytes([0x00, 0x30])
        + bytes([0xA9, 0x00, 0x00, 0x00])
    )


def trace_bytes(writes: Any = (), reads: Any = ()) -> Any:
    blob = b"".join(record(dt.KIND_WRITE, one) for one in writes)
    return blob + b"".join(record(dt.KIND_READ, one) for one in reads)


class PartTest(unittest.TestCase):
    def test_the_part_a_trace_is_replayed_against_is_the_one_the_cartridge_carries(self) -> None:
        self.assertEqual(verify.PART, "dsp2")

    def test_a_machine_with_no_microcode_says_why_rather_than_going_quiet(self) -> None:
        self.assertTrue(verify.why_not() is None or isinstance(verify.why_not(), str))


class BuildTest(unittest.TestCase):
    def test_it_asks_for_the_part_the_cartridge_carries(self) -> None:
        asked: list[Any] = []

        verify.chip(build=asked.append)

        self.assertEqual(asked, [verify.PART])


class CheckTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.bin"
        self.addCleanup(self.tmp.cleanup)

    def test_every_written_byte_reaches_the_part(self) -> None:
        self.path.write_bytes(trace_bytes(writes=(0x09, 0x10)))
        held = Puppet()

        verify.check(self.path, lambda: held)

        self.assertEqual(held.written, [0x09, 0x10])

    def test_a_trace_the_part_reproduces_reports_no_mismatch(self) -> None:
        self.path.write_bytes(trace_bytes(writes=(0x09,), reads=(0x11, 0x22)))

        result = verify.check(self.path, puppets((0x11, 0x22)))

        self.assertEqual(result.mismatches, 0)
        self.assertEqual(result.reads, 2)
        self.assertEqual(result.writes, 1)
        self.assertTrue(result.ok)

    def test_a_single_altered_byte_is_caught(self) -> None:
        self.path.write_bytes(trace_bytes(writes=(0x09,), reads=(0x11, 0x22)))

        result = verify.check(self.path, puppets((0x11, 0xFF)))

        self.assertEqual(result.mismatches, 1)
        self.assertFalse(result.ok)

    def test_and_reported_with_what_both_sides_had(self) -> None:
        self.path.write_bytes(trace_bytes(writes=(0x09,), reads=(0x11,)))

        result = verify.check(self.path, puppets((0xFF,)))

        self.assertEqual(result.examples[0][2], 0x11)
        self.assertEqual(result.examples[0][3], 0xFF)

    def test_no_more_than_a_handful_of_examples_are_kept(self) -> None:
        self.path.write_bytes(trace_bytes(reads=tuple(range(20))))

        result = verify.check(self.path, puppets((0xFF,) * 20))

        self.assertEqual(len(result.examples), verify.EXAMPLE_LIMIT)

    def test_a_trace_with_no_reads_is_still_counted(self) -> None:
        self.path.write_bytes(trace_bytes(writes=(0x0F,)))

        result = verify.check(self.path, puppets())

        self.assertEqual(result.reads, 0)
        self.assertEqual(result.writes, 1)

    def test_a_missing_trace_is_reported_rather_than_raising(self) -> None:
        result = verify.check(Path(self.tmp.name) / "absent.bin", puppets())

        self.assertIsNone(result)


class ExplainTest(unittest.TestCase):
    def test_a_result_says_how_much_went_each_way(self) -> None:
        found = verify.Result(Path("trace.bin"), writes=3, reads=2, mismatches=0, examples=[])

        self.assertIn("3", verify.explain(found))
        self.assertIn("2", verify.explain(found))

    def test_and_lists_the_examples_it_kept(self) -> None:
        found = verify.Result(
            Path("trace.bin"), writes=1, reads=1, mismatches=1, examples=[(7, 0x048000, 1, 2)]
        )

        self.assertIn("frame 7", verify.explain(found))


class MainTest(unittest.TestCase):
    def test_a_machine_with_no_microcode_reports_that_it_had_nothing_to_run(self) -> None:
        said: list[Any] = []

        code = verify.main(["verify_trace.py"], refuses=lambda: "no image is here", say=said.append)

        self.assertEqual(code, 2)
        self.assertIn("nothing to check", " ".join(said))

    def test_no_trace_at_all_is_a_skip_rather_than_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = verify.main(
                ["verify_trace.py", str(Path(tmp) / "nothing.bin")],
                build=puppets(),
                refuses=lambda: None,
                say=lambda _line: None,
            )

        self.assertEqual(code, 0)

    def test_a_trace_the_part_reproduces_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "trace.bin"
            where.write_bytes(trace_bytes(writes=(0x09,), reads=(0x11,)))

            code = verify.main(
                ["verify_trace.py", str(where)],
                build=puppets((0x11,)),
                refuses=lambda: None,
                say=lambda _line: None,
            )

        self.assertEqual(code, 0)

    def test_a_leading_number_bounds_the_run_rather_than_naming_a_trace(self) -> None:
        said: list[Any] = []
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "trace.bin"
            where.write_bytes(trace_bytes(writes=(0x09, 0x0A, 0x0B), reads=(0x11,)))

            verify.main(
                ["verify_trace.py", "2", str(where)],
                build=puppets((0x11,)),
                refuses=lambda: None,
                say=said.append,
            )

        self.assertTrue(any("2 written" in one for one in said))

    def test_and_one_it_does_not_fails(self) -> None:
        said: list[Any] = []
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "trace.bin"
            where.write_bytes(trace_bytes(writes=(0x09,), reads=(0x11,)))

            code = verify.main(
                ["verify_trace.py", str(where)],
                build=puppets((0xFF,)),
                refuses=lambda: None,
                say=said.append,
            )

        self.assertEqual(code, 1)
        self.assertIn("did not reproduce", " ".join(said))


class ProgressTest(unittest.TestCase):
    """A run long enough to outlive a session has to say where it has got to."""

    @override
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.bin"
        self.addCleanup(self.tmp.cleanup)
        self.path.write_bytes(trace_bytes(writes=tuple(range(60))))

    def test_it_reports_as_it_goes(self) -> None:
        said: list[str] = []

        verify.check(self.path, puppets(), say=said.append, every=20)

        self.assertEqual(len(said), 3)

    def test_what_it_says_names_the_trace_and_how_far_it_has_read(self) -> None:
        said: list[str] = []

        verify.check(self.path, puppets(), say=said.append, every=20)

        self.assertIn("trace.bin", said[0])
        self.assertIn("20", said[0])

    def test_a_run_shorter_than_a_step_says_nothing_before_its_result(self) -> None:
        said: list[str] = []

        verify.check(self.path, puppets(), say=said.append, every=1000)

        self.assertEqual(said, [])

    def test_a_limit_stops_the_run_where_it_was_told_to(self) -> None:
        found = verify.check(self.path, puppets(), limit=10)

        self.assertEqual(found.writes + found.reads, 10)

    def test_no_limit_reads_the_whole_trace(self) -> None:
        found = verify.check(self.path, puppets())

        self.assertEqual(found.writes + found.reads, 60)


if __name__ == "__main__":
    unittest.main()
