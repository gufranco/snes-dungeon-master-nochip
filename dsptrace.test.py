import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "dsptrace.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dsptrace", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dt = load_module()

FEED_TRAMPOLINE = 0x0084
DSP_BANK = 0x3F


def record(kind, byte, pc=0x048000, x=0, y=0, frame=0, feed_src=None, drain_dst=0x7E):
    trampolines = bytes([0x00, 0x00, DSP_BANK, 0x00, drain_dst, DSP_BANK, 0x00, 0x00])
    around = (
        bytes([0xA9, 0x00, 0x00, 0x00])
        if feed_src is None
        else bytes([0x54, DSP_BANK, feed_src, 0x00])
    )
    return (
        struct.pack("<II", frame, pc)
        + struct.pack("<HH", x, y)
        + bytes([kind, byte])
        + trampolines
        + bytes([0x00, 0x30])
        + around
    )


def write_trace(path, records):
    Path(path).write_bytes(b"".join(records))


def writes(values, **kwargs):
    return [record(dt.KIND_WRITE, v, **kwargs) for v in values]


def reads(values, **kwargs):
    return [record(dt.KIND_READ, v, **kwargs) for v in values]


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.bin"
        self.addCleanup(self.tmp.cleanup)

    def test_a_record_round_trips_every_field(self):
        write_trace(
            self.path, [record(dt.KIND_WRITE, 0x09, pc=0x0486B7, x=0x1234, y=0x8000, frame=7)]
        )

        got = list(dt.records(self.path))

        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].frame, 7)
        self.assertEqual(got[0].pc, 0x0486B7)
        self.assertEqual(got[0].x, 0x1234)
        self.assertEqual(got[0].y, 0x8000)
        self.assertEqual(got[0].byte, 0x09)
        self.assertEqual(got[0].kind, dt.KIND_WRITE)

    def test_a_truncated_tail_is_refused_rather_than_guessed(self):
        write_trace(self.path, [record(dt.KIND_WRITE, 0x01)])
        self.path.write_bytes(self.path.read_bytes()[:-3])

        with self.assertRaises(dt.TruncatedTrace):
            list(dt.records(self.path))

    def test_the_feed_bank_comes_from_the_block_move_operand(self):
        write_trace(self.path, [record(dt.KIND_WRITE, 0x01, feed_src=0x21)])

        got = list(dt.records(self.path))

        self.assertEqual(got[0].move_source_bank, 0x21)
        self.assertEqual(got[0].move_destination_bank, DSP_BANK)

    def test_a_byte_written_by_an_ordinary_store_reports_no_block_move(self):
        write_trace(self.path, [record(dt.KIND_WRITE, 0x01)])

        got = list(dt.records(self.path))

        self.assertIsNone(got[0].move_source_bank)


class StateMachineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.bin"
        self.addCleanup(self.tmp.cleanup)

    def transactions_of(self, records):
        write_trace(self.path, records)
        return list(dt.transactions(dt.records(self.path)))

    def test_the_boot_sync_is_a_command_with_no_payload(self):
        found = self.transactions_of(writes([0x0F] * 6))

        self.assertEqual([t.command for t in found], [0x0F] * 6)
        self.assertTrue(all(t.parameters == b"" for t in found))

    def test_a_multiply_carries_four_parameters_and_four_outputs(self):
        found = self.transactions_of(
            writes([0x09, 0x10, 0x00, 0x03, 0x00]) + reads([0x30, 0x00, 0x00, 0x00])
        )

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].command, 0x09)
        self.assertEqual(found[0].parameters, bytes([0x10, 0x00, 0x03, 0x00]))
        self.assertEqual(found[0].output, bytes([0x30, 0x00, 0x00, 0x00]))

    def test_a_tile_conversion_carries_thirty_two_each_way(self):
        payload = bytes(range(32))
        found = self.transactions_of(writes([0x01]) + writes(payload) + reads(payload))

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].command, 0x01)
        self.assertEqual(len(found[0].parameters), 32)
        self.assertEqual(len(found[0].output), 32)

    def test_the_transparent_colour_takes_one_parameter_and_returns_nothing(self):
        found = self.transactions_of(writes([0x03, 0x0A]))

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].command, 0x03)
        self.assertEqual(found[0].parameters, bytes([0x0A]))
        self.assertEqual(found[0].output, b"")

    def test_a_merge_reads_its_length_then_twice_that_many_parameters(self):
        found = self.transactions_of(
            writes([0x05, 4]) + writes(bytes(range(8))) + reads(bytes(range(4)))
        )

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].command, 0x05)
        self.assertEqual(found[0].lengths, (4,))
        self.assertEqual(len(found[0].parameters), 8)
        self.assertEqual(len(found[0].output), 4)

    def test_a_mirror_reads_its_length_then_that_many_parameters(self):
        found = self.transactions_of(
            writes([0x06, 5]) + writes(bytes(range(5))) + reads(bytes(range(5)))
        )

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].command, 0x06)
        self.assertEqual(found[0].lengths, (5,))
        self.assertEqual(len(found[0].parameters), 5)

    def test_a_scale_reads_two_lengths_then_half_the_input_rounded_up(self):
        found = self.transactions_of(
            writes([0x0D, 7, 10]) + writes(bytes(range(4))) + reads(bytes(range(10)))
        )

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].command, 0x0D)
        self.assertEqual(found[0].lengths, (7, 10))
        self.assertEqual(len(found[0].parameters), 4)
        self.assertEqual(len(found[0].output), 10)

    def test_two_transactions_in_a_row_are_kept_apart(self):
        found = self.transactions_of(writes([0x03, 0x0A]) + writes([0x03, 0x0B]))

        self.assertEqual([t.parameters for t in found], [bytes([0x0A]), bytes([0x0B])])

    def test_a_transaction_left_open_at_the_end_is_reported_as_incomplete(self):
        found = self.transactions_of(writes([0x09, 0x10, 0x00]))

        self.assertEqual(len(found), 1)
        self.assertFalse(found[0].complete)


class SourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.bin"
        self.addCleanup(self.tmp.cleanup)

    def transactions_of(self, records):
        write_trace(self.path, records)
        return list(dt.transactions(dt.records(self.path)))

    def test_a_block_moved_run_reports_its_source_address(self):
        block = [
            record(dt.KIND_WRITE, value, pc=0x0098C7, x=0x2000 + i, feed_src=0x21)
            for i, value in enumerate(range(32))
        ]
        found = self.transactions_of(writes([0x01], pc=0x009A36) + block + reads(bytes(32)))

        self.assertEqual(found[0].source, (0x21, 0x2000))

    def test_a_run_split_across_several_block_moves_keeps_the_first_address(self):
        block = []
        for row in range(8):
            for column in range(4):
                block.append(
                    record(
                        dt.KIND_WRITE,
                        row * 4 + column,
                        pc=0x0098CA + row * 12,
                        x=0x2000 + row * 84 + column,
                        feed_src=0x7E,
                    )
                )
        found = self.transactions_of(writes([0x01], pc=0x0098BD) + block + reads(bytes(32)))

        self.assertEqual(found[0].source, (0x7E, 0x2000))
        self.assertEqual(found[0].strides, (84,))

    def test_a_run_written_one_byte_at_a_time_has_no_source_address(self):
        found = self.transactions_of(
            writes([0x09, 0x10, 0x00, 0x03, 0x00], pc=0x0486B7) + reads(bytes(4))
        )

        self.assertIsNone(found[0].source)

    def test_a_source_in_work_ram_is_told_apart_from_one_in_rom(self):
        rom_block = [
            record(dt.KIND_WRITE, v, pc=0x04008B, x=0x8000 + i, feed_src=0x09)
            for i, v in enumerate(range(8))
        ]
        ram_block = [
            record(dt.KIND_WRITE, v, pc=0x040087, x=0x4000 + i, feed_src=0x7E)
            for i, v in enumerate(range(8))
        ]
        found = self.transactions_of(
            writes([0x05, 4], pc=0x048875) + ram_block + rom_block + reads(bytes(4))
        )

        self.assertEqual(found[0].source, (0x7E, 0x4000))
        self.assertEqual(found[0].second_source, (0x09, 0x8000))


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.bin"
        self.addCleanup(self.tmp.cleanup)

    def test_counts_are_grouped_by_command(self):
        write_trace(self.path, writes([0x03, 0x0A]) + writes([0x03, 0x0B]) + writes([0x0F]))

        found = dt.summarise(dt.transactions(dt.records(self.path)))

        self.assertEqual(found.per_command[0x03], 2)
        self.assertEqual(found.per_command[0x0F], 1)

    def test_the_program_counters_that_issue_commands_are_collected(self):
        write_trace(self.path, writes([0x03, 0x0A], pc=0x0487EC))

        found = dt.summarise(dt.transactions(dt.records(self.path)))

        self.assertIn(0x0487EC, found.sites)


if __name__ == "__main__":
    unittest.main(verbosity=2)
