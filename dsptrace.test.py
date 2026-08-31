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

    def test_a_scale_reads_two_lengths_then_half_of_each_rounded_up(self):
        found = self.transactions_of(
            writes([0x0D, 7, 10]) + writes(bytes(range(4))) + reads(bytes(range(5)))
        )

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].command, 0x0D)
        self.assertEqual(found[0].lengths, (7, 10))
        self.assertEqual(len(found[0].parameters), 4)
        self.assertEqual(len(found[0].output), 5)

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


class ReportTest(unittest.TestCase):
    """What a summary reads like, since a summary nobody can read is a number."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.bin"
        self.addCleanup(self.tmp.cleanup)

    def _summary(self, records):
        write_trace(self.path, records)
        return dt.summarise(dt.transactions(dt.records(self.path)))

    def test_it_opens_with_how_many_transactions_there_were(self):
        found = dt.report(self._summary(writes([0x0F])))

        self.assertIn("transactions 1", found)

    def test_and_names_every_command_it_saw(self):
        found = dt.report(self._summary(writes([0x03, 0x0A])))

        self.assertIn("transparent", found)

    def test_and_lists_the_sites_that_issued_them(self):
        found = dt.report(self._summary(writes([0x03, 0x0A], pc=0x0487EC)))

        self.assertIn("$0487EC", found)

    def test_a_source_in_work_ram_is_named_as_work_ram(self):
        records = writes([0x05, 0x02], pc=0x048000) + writes([0, 0, 0, 0], feed_src=0x7E)

        found = dt.report(self._summary(records))

        self.assertIn("work RAM", found)

    def test_and_one_outside_it_is_named_as_rom(self):
        records = writes([0x05, 0x02], pc=0x048000) + writes([0, 0, 0, 0], feed_src=0x20)

        found = dt.report(self._summary(records))

        self.assertIn("ROM", found)

    def test_a_command_with_no_name_is_printed_by_its_number(self):
        found = dt.report(self._summary(writes([0x42])))

        self.assertIn("op42", found)

    def test_the_length_tuples_a_run_used_are_counted(self):
        records = writes([0x05, 0x02]) + writes([0] * 4) + reads([0] * 2)

        found = dt.report(self._summary(records))

        self.assertIn("distinct length tuples", found)


class TransactionPrintingTest(unittest.TestCase):
    def test_a_transaction_prints_as_what_it_is(self):
        one = dt.Transaction(frame=7, pc=0x048000, command=0x09)

        self.assertIn("multiply", repr(one))
        self.assertIn("frame=7", repr(one))

    def test_and_says_where_its_input_came_from_when_it_knows(self):
        one = dt.Transaction(frame=0, pc=0, command=0x05)
        one.source = (0x7E, 0x1234)

        self.assertIn("src=$7E:1234", repr(one))

    def test_a_command_with_no_name_prints_by_its_number(self):
        self.assertIn("op42", repr(dt.Transaction(frame=0, pc=0, command=0x42)))

    def test_a_transaction_names_the_banks_its_input_came_from(self):
        one = dt.Transaction(frame=0, pc=0, command=0x05)
        one.source = (0x7E, 0x1234)
        one.second_source = (0x20, 0x8000)

        self.assertEqual(one.source_banks, (0x7E, 0x20))


class WorkRamTest(unittest.TestCase):
    def test_the_two_work_ram_banks_are_known_as_such(self):
        self.assertTrue(dt.is_work_ram(0x7E))
        self.assertTrue(dt.is_work_ram(0x7F))

    def test_and_a_rom_bank_is_not(self):
        self.assertFalse(dt.is_work_ram(0x20))


class PayloadSizeTest(unittest.TestCase):
    """Only three commands declare a length, and a fourth is refused."""

    def test_a_merge_takes_twice_its_length_and_gives_its_length(self):
        self.assertEqual(dt._payload_sizes(0x05, (4,)), (8, 4))

    def test_a_mirror_takes_and_gives_its_length(self):
        self.assertEqual(dt._payload_sizes(0x06, (4,)), (4, 4))

    def test_a_scale_takes_and_gives_half_of_each_length_rounded_up(self):
        self.assertEqual(dt._payload_sizes(0x0D, (5, 9)), (3, 5))

    def test_both_scale_lengths_count_nibbles_rather_than_bytes(self):
        """A recorded scale writes 63 bytes and reads 40.

        The 63 are a command, two lengths and ceil(120 / 2) of payload, so the
        40 read back are ceil(80 / 2). Reading the second length as a count of
        bytes made the parser wait for twice as many, and absorb the next
        command's writes into this one's parameters while it waited.
        """
        self.assertEqual(dt._payload_sizes(0x0D, (120, 80)), (60, 40))

    def test_a_command_that_declares_no_length_is_refused(self):
        with self.assertRaises(dt.UnknownLength):
            dt._payload_sizes(0x09, (4,))


class StreamEdgeTest(unittest.TestCase):
    """Traces begin and end wherever the recorder was turned on and off."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trace.bin"
        self.addCleanup(self.tmp.cleanup)

    def _walk(self, records):
        write_trace(self.path, records)
        return list(dt.transactions(dt.records(self.path)))

    def test_a_read_before_any_command_is_passed_over(self):
        found = self._walk(reads([0xFF]) + writes([0x0F]))

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].command, 0x0F)

    def test_a_length_of_zero_finishes_the_command_where_it_stands(self):
        found = self._walk(writes([0x05, 0x00]))

        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].complete)
        self.assertEqual(found[0].lengths, (0,))

    def test_a_read_arriving_before_the_input_is_done_is_passed_over(self):
        records = writes([0x09, 0x01, 0x02]) + reads([0xFF]) + writes([0x03, 0x04])

        found = self._walk(records + reads([0] * 4))

        self.assertEqual(len(found), 1)
        self.assertEqual(len(found[0].parameters), 4)

    def test_a_command_that_answers_without_taking_anything_is_complete(self):
        found = self._walk(writes([0x0F]))

        self.assertTrue(found[0].complete)

    def test_a_command_nobody_recognises_takes_nothing_and_gives_nothing(self):
        found = self._walk(writes([0x42]))

        self.assertEqual(found[0].parameters, b"")
        self.assertEqual(found[0].output, b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
