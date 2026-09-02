import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import verify_merge  # noqa: E402


class RuleTest(unittest.TestCase):
    def test_a_pixel_matching_the_colour_comes_from_the_first_bitmap(self) -> None:
        self.assertEqual(verify_merge.expected(0xA, b"\xcc", b"\xaa"), b"\xcc")

    def test_a_pixel_not_matching_it_comes_from_the_second(self) -> None:
        self.assertEqual(verify_merge.expected(0x0, b"\xcc", b"\xaa"), b"\xaa")

    def test_the_two_nibbles_are_decided_apart(self) -> None:
        self.assertEqual(verify_merge.expected(0xA, b"\x12", b"\xa5"), b"\x15")

    def test_only_the_low_nibble_of_the_colour_counts(self) -> None:
        self.assertEqual(
            verify_merge.expected(0xFA, b"\xcc", b"\xaa"),
            verify_merge.expected(0x0A, b"\xcc", b"\xaa"),
        )

    def test_every_byte_of_the_run_is_merged(self) -> None:
        self.assertEqual(len(verify_merge.expected(0, b"\x11\x22\x33", b"\x44\x55\x66")), 3)


class CaseTest(unittest.TestCase):
    def test_no_case_declares_a_length_the_part_answers_differently_for(self) -> None:
        lengths = {one.length for one in verify_merge.cases(4)}

        self.assertTrue(max(lengths) <= verify_merge.SAFE_LENGTH)

    def test_the_shortest_run_there_is_gets_tried(self) -> None:
        lengths = {one.length for one in verify_merge.cases(4)}

        self.assertIn(1, lengths)

    def test_the_longest_safe_run_gets_tried(self) -> None:
        lengths = {one.length for one in verify_merge.cases(4)}

        self.assertIn(verify_merge.SAFE_LENGTH, lengths)

    def test_the_cases_are_the_same_every_run(self) -> None:
        first = [(one.colour, one.first, one.second) for one in verify_merge.cases(3)]
        again = [(one.colour, one.first, one.second) for one in verify_merge.cases(3)]

        self.assertEqual(first, again)

    def test_each_bitmap_is_as_long_as_the_run_declares(self) -> None:
        wrong = [one for one in verify_merge.cases(3) if len(one.first) != one.length]

        self.assertEqual(wrong, [])


class ScriptTest(unittest.TestCase):
    def test_a_case_sets_the_colour_before_it_merges(self) -> None:
        one = verify_merge.Case(0x0A, 1, b"\xcc", b"\xaa")

        runs = verify_merge.runs_for([one], lambda case: b"\xcc")

        self.assertEqual(runs[0][1][:2], bytes([0x03, 0x0A]))

    def test_the_merge_declares_its_length(self) -> None:
        one = verify_merge.Case(0x0A, 1, b"\xcc", b"\xaa")

        runs = verify_merge.runs_for([one], lambda case: b"\xcc")

        self.assertEqual(runs[0][1][2:4], bytes([0x05, 1]))

    def test_both_bitmaps_are_sent(self) -> None:
        one = verify_merge.Case(0x0A, 1, b"\xcc", b"\xaa")

        runs = verify_merge.runs_for([one], lambda case: b"\xcc")

        self.assertEqual(runs[0][1][4:], b"\xcc\xaa")

    def test_what_the_part_answered_is_the_read(self) -> None:
        one = verify_merge.Case(0x0A, 1, b"\xcc", b"\xaa")

        runs = verify_merge.runs_for([one], lambda case: b"\xcc")

        self.assertEqual(runs[1][1], b"\xcc")


class AdapterTest(unittest.TestCase):
    def test_an_exchange_sets_the_colour_then_merges(self) -> None:
        class Chip:
            def __init__(self) -> None:
                self.written: list[int] = []

            def write(self, value: int) -> None:
                self.written.append(value)

            def read(self) -> int:
                return 0x77

        part = Chip()
        one = verify_merge.Case(0x0A, 1, b"\xcc", b"\xaa")

        got = verify_merge.answer_from(lambda: part, one)

        self.assertEqual((part.written, got), ([0x03, 0x0A, 0x05, 1, 0xCC, 0xAA], b"\x77"))

    def test_the_part_is_reached_through_the_pinned_model(self) -> None:
        class Loaded:
            @staticmethod
            def Chip(model: str) -> str:
                return f"built {model}"

        self.assertEqual(verify_merge._default_chip(load=lambda name: Loaded()), "built dsp2")

    def test_the_default_answer_builds_a_part_when_it_is_asked(self) -> None:
        class Chip:
            @staticmethod
            def write(value: int) -> None:
                return None

            @staticmethod
            def read() -> int:
                return 0x77

        answer = verify_merge._default_answer_for(build_chip=Chip)

        self.assertEqual(answer(verify_merge.Case(0x0A, 1, b"\xcc", b"\xaa")), b"\x77")

    def test_the_replay_harness_loads(self) -> None:
        self.assertTrue(hasattr(verify_merge._load_replay(), "run_batch"))

    def test_the_walk_reports_what_the_harness_counted(self) -> None:
        class Replay:
            @staticmethod
            def assemble(root: Any, build: Any) -> bytes:
                return b"skeleton"

            @staticmethod
            def run_batch(build: Any, skeleton: Any, runs: Any) -> Any:
                return b"", {"transactions": 4, "compared": 16, "wrong": 0}

        self.assertEqual(verify_merge._default_walk([], load=Replay), (4, 16, 0))


class ReportTest(unittest.TestCase):
    def test_a_clean_run_says_so(self) -> None:
        self.assertIn("none wrong", "\n".join(verify_merge.report(240, 960, 0)))

    def test_a_run_with_a_fault_counts_it(self) -> None:
        self.assertIn("5", "\n".join(verify_merge.report(240, 960, 5)))


class MainTest(unittest.TestCase):
    def test_a_machine_without_the_part_reports_that_rather_than_failing(self) -> None:
        said: list[str] = []

        def refuse() -> Any:
            raise RuntimeError("no microcode")

        self.assertEqual(verify_merge.main((), answer_for=refuse, say=said.append), 0)

    def test_it_says_what_it_could_not_do(self) -> None:
        said: list[str] = []

        def refuse() -> Any:
            raise RuntimeError("no microcode")

        verify_merge.main((), answer_for=refuse, say=said.append)

        self.assertIn("nothing to run", " ".join(said))

    def test_a_clean_run_exits_zero(self) -> None:
        said: list[str] = []

        code = verify_merge.main(
            ("2",),
            answer_for=lambda: faithful,
            walk=lambda runs: (len(runs) // 2, 0, 0),
            say=said.append,
        )

        self.assertEqual(code, 0)

    def test_a_part_that_no_longer_matches_the_written_rule_is_a_failure(self) -> None:
        said: list[str] = []

        code = verify_merge.main(
            ("2",),
            answer_for=lambda: lambda case: b"\x00" * case.length,
            walk=lambda runs: (0, 0, 0),
            say=said.append,
        )

        self.assertEqual(code, 1)

    def test_that_failure_says_the_rule_drifted(self) -> None:
        said: list[str] = []

        verify_merge.main(
            ("2",),
            answer_for=lambda: lambda case: b"\x00" * case.length,
            walk=lambda runs: (0, 0, 0),
            say=said.append,
        )

        self.assertIn("no longer matches the part", " ".join(said))

    def test_a_run_with_a_disagreement_exits_non_zero(self) -> None:
        said: list[str] = []

        code = verify_merge.main(
            ("2",),
            answer_for=lambda: faithful,
            walk=lambda runs: (0, 0, 3),
            say=said.append,
        )

        self.assertEqual(code, 1)


def faithful(case: Any) -> bytes:
    return verify_merge.expected(case.colour, case.first, case.second)


if __name__ == "__main__":
    unittest.main()
