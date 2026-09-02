import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import verify_multiply  # noqa: E402


class RuleTest(unittest.TestCase):
    def test_a_product_of_zero_is_zero(self) -> None:
        self.assertEqual(verify_multiply.expected(0, 6), (0, 0))

    def test_a_small_product_passes_through_unchanged(self) -> None:
        self.assertEqual(verify_multiply.expected(100, 100), (0x2710, 0))

    def test_bit_fourteen_of_the_product_reappears_as_bit_fifteen(self) -> None:
        low, _ = verify_multiply.expected(1000, 1000)

        self.assertEqual(low, 0xC240)

    def test_the_high_word_is_masked(self) -> None:
        _, high = verify_multiply.expected(0xFFFF, 0x7FFF)

        self.assertLessEqual(high, 0x7FFF)

    def test_an_operand_with_its_top_bit_set_is_negative(self) -> None:
        self.assertEqual(verify_multiply.signed(0x8000), -0x8000)

    def test_an_operand_below_that_is_itself(self) -> None:
        self.assertEqual(verify_multiply.signed(0x7FFF), 0x7FFF)


class CaseTest(unittest.TestCase):
    def test_the_edge_cases_are_always_included(self) -> None:
        cases = verify_multiply.cases(0)

        self.assertEqual(list(cases), list(verify_multiply.EDGES))

    def test_asking_for_more_adds_that_many(self) -> None:
        self.assertEqual(len(verify_multiply.cases(10)), len(verify_multiply.EDGES) + 10)

    def test_the_extra_cases_are_the_same_every_run(self) -> None:
        self.assertEqual(verify_multiply.cases(20), verify_multiply.cases(20))

    def test_every_operand_fits_in_a_word(self) -> None:
        flat = [one for pair in verify_multiply.cases(30) for one in pair]

        self.assertTrue(all(0 <= one <= 0xFFFF for one in flat))


class ScriptTest(unittest.TestCase):
    def test_each_case_becomes_a_write_and_a_read(self) -> None:
        runs = verify_multiply.runs_for([(2, 3)], lambda a, b: b"\x06\x00\x00\x00")

        self.assertEqual(len(runs), 2)

    def test_the_write_carries_the_command_and_both_operands(self) -> None:
        runs = verify_multiply.runs_for([(0x1234, 0x5678)], lambda a, b: b"\x00" * 4)

        self.assertEqual(runs[0][1], bytes([0x09, 0x34, 0x12, 0x78, 0x56]))

    def test_the_read_carries_what_the_part_answered(self) -> None:
        runs = verify_multiply.runs_for([(2, 3)], lambda a, b: b"\x06\x00\x00\x00")

        self.assertEqual(runs[1][1], b"\x06\x00\x00\x00")


class ReportTest(unittest.TestCase):
    def test_a_clean_run_says_so(self) -> None:
        said = verify_multiply.report(131, 524, 0)

        self.assertIn("none wrong", "\n".join(said))

    def test_a_run_with_a_fault_counts_it(self) -> None:
        said = verify_multiply.report(131, 524, 3)

        self.assertIn("3", "\n".join(said))

    def test_the_report_names_how_many_pairs_were_tried(self) -> None:
        said = verify_multiply.report(131, 524, 0)

        self.assertIn("131", "\n".join(said))


def faithful(first: int, second: int) -> bytes:
    low, high = verify_multiply.expected(first, second)
    return (low | (high << 16)).to_bytes(4, "little")


class Chip:
    def __init__(self) -> None:
        self.written: list[int] = []
        self.given = [0x40, 0xC2, 0x0F, 0x00]

    def write(self, value: int) -> None:
        self.written.append(value)

    def read(self) -> int:
        return self.given.pop(0)


class AdapterTest(unittest.TestCase):
    def test_an_exchange_writes_the_command_then_both_operands(self) -> None:
        part = Chip()

        verify_multiply.answer_from(lambda: part, 0x1234, 0x5678)

        self.assertEqual(part.written, [0x09, 0x34, 0x12, 0x78, 0x56])

    def test_an_exchange_returns_what_the_part_gave(self) -> None:
        got = verify_multiply.answer_from(Chip, 1000, 1000)

        self.assertEqual(got, bytes([0x40, 0xC2, 0x0F, 0x00]))

    def test_the_default_answer_builds_a_part_when_it_is_asked(self) -> None:
        answer = verify_multiply._default_answer_for(build_chip=Chip)

        self.assertEqual(answer(1000, 1000), bytes([0x40, 0xC2, 0x0F, 0x00]))

    def test_the_walk_reports_what_the_harness_counted(self) -> None:
        class Replay:
            @staticmethod
            def assemble(root: Any, build: Any) -> bytes:
                return b"skeleton"

            @staticmethod
            def run_batch(build: Any, skeleton: Any, runs: Any) -> Any:
                return b"", {"transactions": 7, "compared": 28, "wrong": 0}

        self.assertEqual(verify_multiply._default_walk([], load=Replay), (7, 28, 0))

    def test_the_part_is_reached_through_the_pinned_model(self) -> None:
        class Loaded:
            @staticmethod
            def Chip(model: str) -> str:
                return f"built {model}"

        self.assertEqual(verify_multiply._default_chip(load=lambda name: Loaded()), "built dsp2")

    def test_the_replay_harness_loads(self) -> None:
        self.assertTrue(hasattr(verify_multiply._load_replay(), "run_batch"))


class MainTest(unittest.TestCase):
    def test_a_machine_without_the_part_reports_that_rather_than_failing(self) -> None:
        said: list[str] = []

        def refuse() -> Any:
            raise RuntimeError("no microcode")

        code = verify_multiply.main((), answer_for=refuse, say=said.append)

        self.assertEqual(code, 0)

    def test_it_says_what_it_could_not_do(self) -> None:
        said: list[str] = []

        def refuse() -> Any:
            raise RuntimeError("no microcode")

        verify_multiply.main((), answer_for=refuse, say=said.append)

        self.assertIn("nothing to run", " ".join(said))

    def test_a_clean_run_exits_zero(self) -> None:
        said: list[str] = []

        code = verify_multiply.main(
            (),
            answer_for=lambda: faithful,
            walk=lambda runs: (len(runs) // 2, len(runs) // 2 * 4, 0),
            say=said.append,
        )

        self.assertEqual(code, 0)

    def test_a_part_that_no_longer_matches_the_written_rule_is_a_failure(self) -> None:
        said: list[str] = []

        code = verify_multiply.main(
            (),
            answer_for=lambda: lambda a, b: b"\x00" * 4,
            walk=lambda runs: (0, 0, 0),
            say=said.append,
        )

        self.assertEqual(code, 1)

    def test_that_failure_says_the_rule_drifted(self) -> None:
        said: list[str] = []

        verify_multiply.main(
            (),
            answer_for=lambda: lambda a, b: b"\x00" * 4,
            walk=lambda runs: (0, 0, 0),
            say=said.append,
        )

        self.assertIn("no longer matches the part", " ".join(said))

    def test_a_run_with_a_disagreement_exits_non_zero(self) -> None:
        said: list[str] = []

        code = verify_multiply.main(
            (),
            answer_for=lambda: faithful,
            walk=lambda runs: (len(runs) // 2, len(runs) // 2 * 4, 2),
            say=said.append,
        )

        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
