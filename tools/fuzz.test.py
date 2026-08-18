import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fuzz = load_module("fuzz", ROOT / "tools" / "fuzz.py")


class CaseTest(unittest.TestCase):
    def test_the_same_seed_gives_the_same_cases(self):
        self.assertEqual(fuzz.build_cases(7, 40), fuzz.build_cases(7, 40))

    def test_a_different_seed_gives_different_cases(self):
        self.assertNotEqual(fuzz.build_cases(1, 40), fuzz.build_cases(2, 40))

    def test_every_command_the_chip_knows_is_reached(self):
        commands = {case.command for case in fuzz.build_cases(3, 600)}

        for command in fuzz.COMMANDS:
            self.assertIn(command, commands)

    def test_a_case_carries_the_bytes_that_were_written(self):
        for case in fuzz.build_cases(5, 60):
            self.assertEqual(case.written[0], case.command)

    def test_a_tile_conversion_never_expects_more_than_it_makes(self):
        cases = [case for case in fuzz.build_cases(13, 400) if case.command == fuzz.TILE]

        self.assertTrue(cases)
        for case in cases:
            self.assertLessEqual(len(case.expected), 32)

    def test_a_merge_never_expects_more_than_its_declared_length(self):
        cases = [case for case in fuzz.build_cases(17, 400) if case.command == fuzz.MERGE]

        self.assertTrue(cases)
        for case in cases:
            self.assertLessEqual(len(case.expected), case.lengths[0])

    def test_some_results_are_read_only_in_part(self):
        cases = fuzz.build_cases(37, 800)

        partial = [case for case in cases if case.command == fuzz.TILE and len(case.expected) < 32]

        self.assertTrue(partial)

    def test_a_command_that_makes_nothing_can_still_carry_a_rewound_result(self):
        cases = fuzz.build_cases(41, 800)

        self.assertTrue(any(case.command == fuzz.SYNC and case.expected for case in cases))


class EdgeTest(unittest.TestCase):
    def test_the_shortest_and_longest_merge_are_both_generated(self):
        lengths = {
            case.lengths[0] for case in fuzz.build_cases(19, 4000) if case.command == fuzz.MERGE
        }

        self.assertIn(1, lengths)
        self.assertIn(255, lengths)

    def test_every_transparent_colour_is_set_at_some_point(self):
        seen = {
            case.written[1]
            for case in fuzz.build_cases(23, 4000)
            if case.command == fuzz.TRANSPARENT
        }

        self.assertGreaterEqual(len(seen), 16)


class RunTest(unittest.TestCase):
    def test_cases_become_alternating_feed_and_check_runs(self):
        cases = fuzz.build_cases(29, 20)

        runs = fuzz.runs_for(cases)

        self.assertTrue(runs)
        self.assertEqual(runs[0][0], fuzz.replay.KIND_WRITE)

    def test_a_case_with_no_output_contributes_no_check(self):
        case = fuzz.Case(fuzz.SYNC, (), b"\x0f", b"")

        self.assertEqual(fuzz.runs_for([case]), [(fuzz.replay.KIND_WRITE, b"\x0f")])

    def test_the_bytes_written_reach_the_runs_unchanged(self):
        cases = fuzz.build_cases(31, 30)

        written = b"".join(
            payload for kind, payload in fuzz.runs_for(cases) if kind == fuzz.replay.KIND_WRITE
        )

        self.assertEqual(written, b"".join(case.written for case in cases))


if __name__ == "__main__":
    unittest.main(verbosity=2)
