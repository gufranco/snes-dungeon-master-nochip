import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selftest = load_module("selftest", ROOT / "tools" / "selftest.py")


class ScriptTest(unittest.TestCase):
    def test_a_case_feeds_its_bytes_and_reads_its_output(self):
        script = selftest.build_script([selftest.Case(b"\x0f", 0)])

        self.assertEqual(script[0], selftest.FEED)
        self.assertEqual(script[1:3], (1).to_bytes(2, "little"))
        self.assertEqual(script[3], 0x0F)

    def test_a_case_with_no_output_asks_for_none(self):
        script = selftest.build_script([selftest.Case(b"\x0f", 0)])

        self.assertNotIn(selftest.DRAIN, script[:4])

    def test_a_case_with_output_asks_for_exactly_that_many(self):
        script = selftest.build_script([selftest.Case(b"\x01" + bytes(32), 32)])

        tail = script[-4:]

        self.assertEqual(tail[0], selftest.DRAIN)
        self.assertEqual(tail[1:3], (32).to_bytes(2, "little"))
        self.assertEqual(tail[3], selftest.END)

    def test_the_script_ends_with_the_stop_marker(self):
        self.assertEqual(selftest.build_script([])[-1], selftest.END)

    def test_cases_appear_in_the_order_given(self):
        script = selftest.build_script([selftest.Case(b"\xaa", 0), selftest.Case(b"\xbb", 0)])

        self.assertLess(script.index(b"\xaa"), script.index(b"\xbb"))

    def test_a_script_that_would_overrun_its_bank_is_refused(self):
        with self.assertRaises(selftest.ScriptTooLong):
            selftest.build_script([selftest.Case(bytes(0x8000), 0)])


class ExpectationTest(unittest.TestCase):
    def test_the_expected_bytes_are_the_outputs_in_order(self):
        cases = [selftest.Case(b"\x0f", 0, b""), selftest.Case(b"\x03\x0a", 0, b"")]

        self.assertEqual(selftest.expected(cases), b"")

    def test_every_output_is_concatenated(self):
        cases = [selftest.Case(b"", 2, b"\x01\x02"), selftest.Case(b"", 1, b"\x03")]

        self.assertEqual(selftest.expected(cases), b"\x01\x02\x03")


class ComparisonTest(unittest.TestCase):
    def test_matching_output_reports_nothing(self):
        cases = [selftest.Case(b"", 2, b"\x01\x02")]

        self.assertEqual(selftest.compare(cases, b"\x01\x02"), [])

    def test_a_differing_byte_names_its_case_and_position(self):
        cases = [selftest.Case(b"", 2, b"\x01\x02")]

        found = selftest.compare(cases, b"\x01\xff")

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][1], 1)

    def test_a_short_run_is_reported_rather_than_passing_quietly(self):
        cases = [selftest.Case(b"", 2, b"\x01\x02")]

        found = selftest.compare(cases, b"\x01")

        self.assertTrue(found)


class OutputSizeTest(unittest.TestCase):
    def test_a_merge_returns_its_declared_length(self):
        self.assertEqual(selftest.output_size(selftest.COMMAND_MERGE, (22,)), 22)

    def test_a_scale_returns_its_second_declared_length(self):
        self.assertEqual(selftest.output_size(selftest.COMMAND_SCALE, (120, 80)), 80)

    def test_a_tile_conversion_always_returns_thirty_two(self):
        self.assertEqual(selftest.output_size(selftest.COMMAND_TILE, ()), 32)

    def test_a_sync_returns_nothing(self):
        self.assertEqual(selftest.output_size(selftest.COMMAND_SYNC, ()), 0)


class CarriedStateTest(unittest.TestCase):
    def test_the_transparent_colour_set_by_one_case_reaches_the_next(self):
        alone = selftest.case_for(0x05, (4,), b"\x00\x00\x00\xcc\x00\xaa\xaa\xaa")

        run = selftest.cases_for(
            [
                (0x03, (), b"\x0a"),
                (0x05, (4,), b"\x00\x00\x00\xcc\x00\xaa\xaa\xaa"),
            ]
        )

        self.assertNotEqual(alone.output, run[1].output)

    def test_a_run_keeps_one_case_per_transaction(self):
        run = selftest.cases_for([(0x0F, (), b""), (0x03, (), b"\x0a")])

        self.assertEqual(len(run), 2)


class ModelTest(unittest.TestCase):
    def test_a_case_built_from_the_model_carries_the_model_s_answer(self):
        case = selftest.case_for(0x03, (), b"\x0a")

        self.assertEqual(case.output, b"")

    def test_a_multiply_case_carries_four_bytes_of_answer(self):
        case = selftest.case_for(0x09, (), b"\x02\x00\x03\x00")

        self.assertEqual(len(case.output), 4)

    def test_a_tile_case_carries_thirty_two_bytes_of_answer(self):
        case = selftest.case_for(0x01, (), bytes(range(32)))

        self.assertEqual(len(case.output), 32)

    def test_a_merge_case_declares_its_length_before_its_payload(self):
        case = selftest.case_for(0x05, (4,), bytes(8))

        self.assertEqual(case.feed[:2], b"\x05\x04")
        self.assertEqual(len(case.output), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
