import importlib.util
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fuzz = load_module("fuzz", ROOT / "tools" / "fuzz.py")


class Puppet:
    """A part that counts up, so the generator can be checked without microcode.

    What a real DSP-2 answers is settled by running the cartridge's own program,
    which is what `fuzz.py` does on a machine that has it. What these tests pin
    is the generation: which commands are reached, how long the payloads are,
    where a result is read only in part, and that the bytes written reach the
    runs unchanged. None of that depends on the values coming back.
    """

    def __init__(self) -> None:
        self.written = []
        self.given = 0

    def write(self, value: Any) -> None:
        self.written.append(value)

    def read(self):
        self.given += 1
        return self.given & 0xFF


def puppets():
    def build():
        return Puppet()

    return build


def generated(seed, count, only=None):
    return fuzz.build_cases(seed, count, only, puppets())


class CaseTest(unittest.TestCase):
    def test_the_same_seed_gives_the_same_cases(self) -> None:
        self.assertEqual(generated(7, 40), generated(7, 40))

    def test_a_different_seed_gives_different_cases(self) -> None:
        self.assertNotEqual(generated(1, 40), generated(2, 40))

    def test_every_command_the_chip_knows_is_reached(self) -> None:
        commands = {case.command for case in generated(3, 600)}

        for command in fuzz.COMMANDS:
            self.assertIn(command, commands)

    def test_a_case_carries_the_bytes_that_were_written(self) -> None:
        for case in generated(5, 60):
            self.assertEqual(case.written[0], case.command)

    def test_a_tile_conversion_never_expects_more_than_it_makes(self) -> None:
        cases = [case for case in generated(13, 400) if case.command == fuzz.TILE]

        self.assertTrue(cases)
        for case in cases:
            self.assertLessEqual(len(case.expected), 32)

    def test_a_merge_never_expects_more_than_its_declared_length(self) -> None:
        cases = [case for case in generated(17, 400) if case.command == fuzz.MERGE]

        self.assertTrue(cases)
        for case in cases:
            self.assertLessEqual(len(case.expected), case.lengths[0])

    def test_some_results_are_read_only_in_part(self) -> None:
        cases = generated(37, 800)

        partial = [case for case in cases if case.command == fuzz.TILE and len(case.expected) < 32]

        self.assertTrue(partial)

    def test_a_command_that_makes_nothing_can_still_carry_a_rewound_result(self) -> None:
        cases = generated(41, 800)

        self.assertTrue(any(case.command == fuzz.SYNC and case.expected for case in cases))


class EdgeTest(unittest.TestCase):
    def test_the_shortest_and_longest_merge_are_both_generated(self) -> None:
        lengths = {case.lengths[0] for case in generated(19, 4000) if case.command == fuzz.MERGE}

        self.assertIn(1, lengths)
        self.assertIn(255, lengths)

    def test_every_transparent_colour_is_set_at_some_point(self) -> None:
        seen = {case.written[1] for case in generated(23, 4000) if case.command == fuzz.TRANSPARENT}

        self.assertGreaterEqual(len(seen), 16)


class RunTest(unittest.TestCase):
    def test_cases_become_alternating_feed_and_check_runs(self) -> None:
        cases = generated(29, 20)

        runs = fuzz.runs_for(cases)

        self.assertTrue(runs)
        self.assertEqual(runs[0][0], fuzz.replay.KIND_WRITE)

    def test_a_case_with_no_output_contributes_no_check(self) -> None:
        case = fuzz.Case(fuzz.SYNC, (), b"\x0f", b"")

        self.assertEqual(fuzz.runs_for([case]), [(fuzz.replay.KIND_WRITE, b"\x0f")])

    def test_the_bytes_written_reach_the_runs_unchanged(self) -> None:
        cases = generated(31, 30)

        written = b"".join(
            payload for kind, payload in fuzz.runs_for(cases) if kind == fuzz.replay.KIND_WRITE
        )

        self.assertEqual(written, b"".join(case.written for case in cases))


def a_batch(finished=True, wrong=0, compared=4, transactions=2):
    return {
        "finished": finished,
        "wrong": wrong,
        "compared": compared,
        "transactions": transactions,
        "first": 0,
        "expected": 0x11,
        "returned": 0x22,
    }


class PartTest(unittest.TestCase):
    def test_it_asks_for_the_part_this_cartridge_carries(self) -> None:
        asked = []

        fuzz.chip(build=asked.append)

        self.assertEqual(asked, [fuzz.PART])

    def test_and_a_refusal_comes_from_the_model_rather_than_from_here(self) -> None:
        made_up = type("Model", (), {"why_not": staticmethod(lambda: "no image is here")})

        self.assertEqual(fuzz.why_not(made_up), "no image is here")


class WalkTest(unittest.TestCase):
    """Every batch through the cartridge, and what a batch that stops means."""

    def test_a_run_where_every_batch_finishes_reports_what_it_checked(self) -> None:
        found = fuzz.walk(
            None, b"", [["one"], ["two"]], lambda *_: (b"script", a_batch()), lambda _l: None, int
        )

        self.assertEqual(found[0], 4)
        self.assertEqual(found[1], 8)
        self.assertEqual(found[2], 0)

    def test_a_batch_that_does_not_finish_ends_the_run(self) -> None:
        said = []

        found = fuzz.walk(
            None,
            b"",
            [["one"]],
            lambda *_: (b"script", a_batch(finished=False)),
            said.append,
            int,
        )

        self.assertIsNone(found)
        self.assertIn("did not finish", said[0])

    def test_a_batch_with_disagreements_is_kept_for_the_summary(self) -> None:
        found = fuzz.walk(
            None, b"", [["one"]], lambda *_: (b"script", a_batch(wrong=3)), lambda _l: None, int
        )

        self.assertEqual(found[2], 3)
        self.assertEqual(len(found[3]), 1)


class SummaryTest(unittest.TestCase):
    def test_every_command_the_part_knows_is_named(self) -> None:
        lines = "\n".join(fuzz.summary_lines(generated(3, 200), 1, 2, 0, []))

        for name in ("tile", "merge", "sync"):
            self.assertIn(name, lines)

    def test_a_command_the_part_does_not_know_is_counted_apart(self) -> None:
        cases = [case for case in generated(3, 400) if case.command not in fuzz.COMMANDS]
        lines = "\n".join(fuzz.summary_lines(cases, 0, 0, 0, []))

        self.assertIn("unrecognised", lines)

    def test_what_was_walked_and_checked_is_reported(self) -> None:
        lines = "\n".join(fuzz.summary_lines([], 7, 9, 0, []))

        self.assertIn("runs walked   7", lines)
        self.assertIn("bytes checked 9", lines)

    def test_a_disagreement_names_what_both_sides_had(self) -> None:
        lines = "\n".join(fuzz.summary_lines([], 1, 1, 1, [(0, a_batch(wrong=1))]))

        self.assertIn("part $11", lines)
        self.assertIn("routines $22", lines)

    def test_no_more_than_a_handful_of_batches_are_listed(self) -> None:
        failures = [(number, a_batch(wrong=1)) for number in range(20)]

        lines = fuzz.summary_lines([], 1, 1, 20, failures)

        self.assertEqual(sum(1 for line in lines if "first at byte" in line), 5)


class EntryTest(unittest.TestCase):
    def test_a_machine_with_no_microcode_says_so_rather_than_building_anything(self) -> None:
        said = []

        code = fuzz.main([], refuses=lambda: "no image is here", say=said.append)

        self.assertEqual(code, 2)
        self.assertIn("nothing to build", said[0])

    def test_a_run_where_everything_agrees_passes(self) -> None:
        code = fuzz.main(
            ["1", "20"],
            refuses=lambda: None,
            assemble=lambda *_: b"skeleton",
            run_batch=lambda *_: (b"script", a_batch()),
            generate=lambda *_args: generated(1, 20),
            say=lambda _l: None,
            clock=int,
        )

        self.assertEqual(code, 0)

    def test_a_run_with_a_disagreement_fails(self) -> None:
        code = fuzz.main(
            ["1", "20"],
            refuses=lambda: None,
            assemble=lambda *_: b"skeleton",
            run_batch=lambda *_: (b"script", a_batch(wrong=1)),
            generate=lambda *_args: generated(1, 20),
            say=lambda _l: None,
            clock=int,
        )

        self.assertEqual(code, 1)

    def test_a_batch_that_does_not_finish_fails_too(self) -> None:
        code = fuzz.main(
            ["1", "20"],
            refuses=lambda: None,
            assemble=lambda *_: b"skeleton",
            run_batch=lambda *_: (b"script", a_batch(finished=False)),
            generate=lambda *_args: generated(1, 20),
            say=lambda _l: None,
            clock=int,
        )

        self.assertEqual(code, 1)

    def test_the_commands_to_generate_are_taken_from_the_command_line(self) -> None:
        asked = []

        fuzz.main(
            ["7", "10", "0x05"],
            refuses=lambda: None,
            assemble=lambda *_: b"skeleton",
            run_batch=lambda *_: (b"script", a_batch()),
            generate=lambda seed, count, only: asked.append((seed, count, only)) or generated(1, 5),
            say=lambda _l: None,
            clock=int,
        )

        self.assertEqual(asked, [(7, 10, [0x05])])


if __name__ == "__main__":
    unittest.main(verbosity=2)
