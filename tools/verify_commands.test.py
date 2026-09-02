import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import verify_commands  # noqa: E402


class Chip:
    def __init__(self, given: int = 0x77) -> None:
        self.written: list[int] = []
        self.given = given

    def write(self, value: int) -> None:
        self.written.append(value)

    def read(self) -> int:
        return self.given


class CaseTest(unittest.TestCase):
    def test_a_tile_case_sends_the_fixed_payload(self) -> None:
        one = verify_commands.cases(1)[0]

        self.assertEqual(len(one.payload), verify_commands.TILE_BYTES)

    def test_every_tile_case_reads_back_the_same_width(self) -> None:
        tiles = [one for one in verify_commands.cases(2) if one.command == verify_commands.TILE]

        self.assertTrue(all(one.reads == verify_commands.TILE_BYTES for one in tiles))

    def test_mirror_cases_cover_a_range_of_lengths(self) -> None:
        mirrors = [one for one in verify_commands.cases(2) if one.command == verify_commands.MIRROR]
        lengths = {one.reads for one in mirrors}

        self.assertGreater(len(lengths), 4)

    def test_a_mirror_declares_the_length_it_sends(self) -> None:
        mirrors = [one for one in verify_commands.cases(1) if one.command == verify_commands.MIRROR]
        one = mirrors[0]

        self.assertEqual(one.lengths, (one.reads,))

    def test_no_mirror_goes_past_the_length_the_part_still_agrees_at(self) -> None:
        mirrors = [one for one in verify_commands.cases(2) if one.command == verify_commands.MIRROR]

        self.assertTrue(all(one.reads <= verify_commands.SAFE_LENGTH for one in mirrors))

    def test_the_cases_are_the_same_every_run(self) -> None:
        first = [(one.command, one.payload) for one in verify_commands.cases(2)]
        again = [(one.command, one.payload) for one in verify_commands.cases(2)]

        self.assertEqual(first, again)

    def test_both_commands_are_covered(self) -> None:
        commands = {one.command for one in verify_commands.cases(1)}

        self.assertEqual(commands, {verify_commands.TILE, verify_commands.MIRROR})


class ExchangeTest(unittest.TestCase):
    def test_a_case_writes_its_command_then_its_lengths_then_its_payload(self) -> None:
        part = Chip()
        one = verify_commands.Case(verify_commands.MIRROR, (2,), b"\x11\x12", 2)

        verify_commands.answer_from(lambda: part, one)

        self.assertEqual(part.written, [verify_commands.MIRROR, 2, 0x11, 0x12])

    def test_it_reads_back_what_the_case_asks_for(self) -> None:
        one = verify_commands.Case(verify_commands.MIRROR, (2,), b"\x11\x12", 2)

        got = verify_commands.answer_from(Chip, one)

        self.assertEqual(got, b"\x77\x77")

    def test_a_case_with_no_length_writes_none(self) -> None:
        part = Chip()
        one = verify_commands.Case(verify_commands.TILE, (), b"\x01", 1)

        verify_commands.answer_from(lambda: part, one)

        self.assertEqual(part.written, [verify_commands.TILE, 0x01])


class ScriptTest(unittest.TestCase):
    def test_each_case_becomes_a_write_and_a_read(self) -> None:
        one = verify_commands.Case(verify_commands.MIRROR, (1,), b"\x11", 1)

        runs = verify_commands.runs_for([one], lambda case: b"\x11")

        self.assertEqual(len(runs), 2)

    def test_the_write_carries_command_lengths_and_payload(self) -> None:
        one = verify_commands.Case(verify_commands.MIRROR, (1,), b"\x11", 1)

        runs = verify_commands.runs_for([one], lambda case: b"\x11")

        self.assertEqual(runs[0][1], bytes([verify_commands.MIRROR, 1, 0x11]))

    def test_the_read_carries_what_the_part_answered(self) -> None:
        one = verify_commands.Case(verify_commands.MIRROR, (1,), b"\x11", 1)

        runs = verify_commands.runs_for([one], lambda case: b"\x99")

        self.assertEqual(runs[1][1], b"\x99")


class AdapterTest(unittest.TestCase):
    def test_the_part_is_reached_through_the_pinned_model(self) -> None:
        class Loaded:
            @staticmethod
            def Chip(model: str) -> str:
                return f"built {model}"

        self.assertEqual(verify_commands._default_chip(load=lambda name: Loaded()), "built dsp2")

    def test_the_default_answer_builds_a_part_when_it_is_asked(self) -> None:
        answer = verify_commands._default_answer_for(build_chip=Chip)
        one = verify_commands.Case(verify_commands.MIRROR, (1,), b"\x11", 1)

        self.assertEqual(answer(one), b"\x77")

    def test_the_replay_harness_loads(self) -> None:
        self.assertTrue(hasattr(verify_commands._load_replay(), "run_batch"))

    def test_the_walk_reports_what_the_harness_counted(self) -> None:
        class Replay:
            @staticmethod
            def assemble(root: Any, build: Any) -> bytes:
                return b"skeleton"

            @staticmethod
            def run_batch(build: Any, skeleton: Any, runs: Any) -> Any:
                return b"", {"transactions": 9, "compared": 36, "wrong": 0}

        self.assertEqual(verify_commands._default_walk([], load=Replay), (9, 36, 0))


class ReportTest(unittest.TestCase):
    def test_a_clean_run_says_so(self) -> None:
        self.assertIn("none wrong", "\n".join(verify_commands.report(60, 900, 0)))

    def test_a_run_with_a_fault_counts_it(self) -> None:
        self.assertIn("7", "\n".join(verify_commands.report(60, 900, 7)))


class MainTest(unittest.TestCase):
    def test_a_machine_without_the_part_reports_that_rather_than_failing(self) -> None:
        said: list[str] = []

        def refuse() -> Any:
            raise RuntimeError("no microcode")

        self.assertEqual(verify_commands.main((), answer_for=refuse, say=said.append), 0)

    def test_it_says_what_it_could_not_do(self) -> None:
        said: list[str] = []

        def refuse() -> Any:
            raise RuntimeError("no microcode")

        verify_commands.main((), answer_for=refuse, say=said.append)

        self.assertIn("nothing to run", " ".join(said))

    def test_a_clean_run_exits_zero(self) -> None:
        said: list[str] = []

        code = verify_commands.main(
            ("1",),
            answer_for=lambda: lambda case: b"\x00" * case.reads,
            walk=lambda runs: (len(runs) // 2, 0, 0),
            say=said.append,
        )

        self.assertEqual(code, 0)

    def test_a_run_with_a_disagreement_exits_non_zero(self) -> None:
        said: list[str] = []

        code = verify_commands.main(
            ("1",),
            answer_for=lambda: lambda case: b"\x00" * case.reads,
            walk=lambda runs: (0, 0, 4),
            say=said.append,
        )

        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
