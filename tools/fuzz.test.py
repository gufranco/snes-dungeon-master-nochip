import importlib.util
import struct
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fuzz = load_module("fuzz", ROOT / "tools" / "fuzz.py")


def _recording_generate(seen: list[Any], make: Any) -> Any:
    """A stand-in for case generation that keeps what it was asked for."""

    def _generate(seed: int, count: int, only: Any) -> Any:
        seen.append((seed, count, only))
        return make(1, 5)

    return _generate


class Puppet:
    """A part that counts up, so the generator can be checked without microcode.

    What a real DSP-2 answers is settled by running the cartridge's own program,
    which is what `fuzz.py` does on a machine that has it. What these tests pin
    is the generation: which commands are reached, how long the payloads are,
    where a result is read only in part, and that the bytes written reach the
    runs unchanged. None of that depends on the values coming back.
    """

    def __init__(self) -> None:
        self.written: list[Any] = []
        self.given = 0

    def write(self, value: Any) -> None:
        self.written.append(value)

    def read(self) -> Any:
        self.given += 1
        return self.given & 0xFF


def puppets() -> Any:
    def build() -> Any:
        return Puppet()

    return build


def generated(seed: Any, count: Any, only: Any = None) -> Any:
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

    def test_a_colour_is_always_one_of_the_sixteen_there_are(self) -> None:
        seen = {case.written[1] for case in generated(23, 2000) if case.command == fuzz.TRANSPARENT}

        self.assertTrue(all(one < 16 for one in seen), sorted(seen))

    def test_the_first_case_sets_a_colour(self) -> None:
        first = generated(59, 30)[0]

        self.assertEqual(first.command, fuzz.TRANSPARENT)

    def test_nothing_merges_before_a_colour_has_been_set(self) -> None:
        cases = generated(61, 200)

        first_colour = next(i for i, one in enumerate(cases) if one.command == fuzz.TRANSPARENT)
        first_merge = next(i for i, one in enumerate(cases) if one.command == fuzz.MERGE)
        self.assertLess(first_colour, first_merge)

    def test_the_opening_colour_is_set_even_when_no_others_are_asked_for(self) -> None:
        cases = generated(67, 20, only=[fuzz.MERGE])

        self.assertEqual(cases[0].command, fuzz.TRANSPARENT)


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


def a_batch(
    finished: Any = True,
    wrong: Any = 0,
    compared: Any = 4,
    transactions: Any = 2,
) -> Any:
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
        asked: list[Any] = []

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
        said: list[Any] = []

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


def a_sound_oracle() -> dict[str, Any]:
    """A calibration that trusts every command, for tests about anything else."""
    return {name: fuzz.Reading(True, True) for name in fuzz.NAMES.values()}


class EntryTest(unittest.TestCase):
    def test_a_machine_with_no_microcode_says_so_rather_than_building_anything(self) -> None:
        said: list[Any] = []

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
            checked=a_sound_oracle,
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
            checked=a_sound_oracle,
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
            checked=a_sound_oracle,
        )

        self.assertEqual(code, 1)

    def test_the_commands_to_generate_are_taken_from_the_command_line(self) -> None:
        asked: list[Any] = []

        fuzz.main(
            ["7", "10", "0x05"],
            refuses=lambda: None,
            assemble=lambda *_: b"skeleton",
            run_batch=lambda *_: (b"script", a_batch()),
            generate=_recording_generate(asked, generated),
            say=lambda _l: None,
            clock=int,
            checked=a_sound_oracle,
        )

        self.assertEqual(asked, [(7, 10, [0x05])])


Exchange = namedtuple("Exchange", "name command lengths parameters output complete")

COMMAND_BYTES = frozenset(
    (fuzz.TILE, fuzz.TRANSPARENT, fuzz.MERGE, fuzz.MIRROR, fuzz.MULTIPLY, fuzz.SCALE, fuzz.SYNC)
)


def an_exchange(name: str, command: int, output: bytes = b"\x11\x22", complete: bool = True) -> Any:
    return Exchange(name, command, (), b"\x80\x81", output, complete)


COLOUR = an_exchange("transparent", fuzz.TRANSPARENT, b"")
RECORDED = {
    "tile": an_exchange("tile", fuzz.TILE),
    "merge": an_exchange("merge", fuzz.MERGE),
    "mirror": an_exchange("mirror", fuzz.MIRROR),
    "multiply": an_exchange("multiply", fuzz.MULTIPLY),
    "scale": an_exchange("scale", fuzz.SCALE),
    "sync": an_exchange("sync", fuzz.SYNC, b""),
}


KIND_WRITE = 0
KIND_READ = 1
DSP_BANK = 0x3F


def a_record(kind: int, byte: int) -> bytes:
    """One port access in the shape the recorder wrote it."""
    return (
        struct.pack("<II", 0, 294912)
        + struct.pack("<HH", 0, 0)
        + bytes([kind, byte])
        + bytes([0x00, 0x00, DSP_BANK, 0x00, 126, DSP_BANK, 0x00, 0x00])
        + bytes([0x00, 0x30])
        + bytes([0xA9, 0x00, 0x00, 0x00])
    )


def a_recorded_mirror() -> list[bytes]:
    """One complete mirror on the port, which is the least a calibration needs."""
    written = [a_record(KIND_WRITE, byte) for byte in (fuzz.MIRROR, 0x02, 0x12, 0x34)]
    return [*written, *(a_record(KIND_READ, byte) for byte in (0x43, 0x21))]


class Oracle:
    """A part that answers correctly until it is asked for a command it gets wrong.

    Two failures are worth telling apart and only one of them is visible in the
    answer. A command the model computes wrongly is caught by comparing that
    command. A command that leaves the model owing a byte the cartridge never
    took answers correctly itself and breaks everything after it, so it is
    caught only by asking again afterwards.
    """

    def __init__(self, wrong: tuple[int, ...] = (), poisons: tuple[int, ...] = ()) -> None:
        self.wrong = wrong
        self.poisons = poisons
        self.spoiled = False
        self.command: int | None = None
        self.given = 0

    def write(self, byte: int) -> None:
        if byte not in COMMAND_BYTES:
            return
        if self.command in self.poisons:
            self.spoiled = True
        self.command = byte
        self.given = 0

    def read(self) -> int:
        self.given += 1
        if self.spoiled or self.command in self.wrong:
            return 0xFF
        return 0x11 if self.given == 1 else 0x22


def an_oracle(wrong: tuple[int, ...] = (), poisons: tuple[int, ...] = ()) -> Any:
    """A part built fresh, so a calibration gets one that has not been spoiled."""

    def build() -> Any:
        return Oracle(wrong, poisons)

    return build


class SampleTest(unittest.TestCase):
    """One recorded exchange per command, taken out of a trace."""

    def test_each_named_command_contributes_one(self) -> None:
        colour, found = fuzz.sample([COLOUR, *RECORDED.values()], ("tile", "mirror"))

        self.assertEqual((sorted(found), colour), (["mirror", "tile"], COLOUR))

    def test_the_first_of_each_is_the_one_taken(self) -> None:
        first = an_exchange("mirror", fuzz.MIRROR, b"\xaa\xbb")
        second = an_exchange("mirror", fuzz.MIRROR, b"\xcc\xdd")

        _colour, found = fuzz.sample([first, second], ("mirror",))

        self.assertIs(found["mirror"], first)

    def test_an_incomplete_exchange_is_not_taken(self) -> None:
        broken = an_exchange("mirror", fuzz.MIRROR, complete=False)

        _colour, found = fuzz.sample([broken], ("mirror",))

        self.assertEqual(found, {})

    def test_a_command_the_trace_never_carried_is_simply_absent(self) -> None:
        _colour, found = fuzz.sample([RECORDED["mirror"]], ("tile", "mirror"))

        self.assertEqual(sorted(found), ["mirror"])


class CalibrateTest(unittest.TestCase):
    """Which commands the oracle can be trusted for."""

    def reading(self, wrong: tuple[int, ...] = (), poisons: tuple[int, ...] = ()) -> Any:
        return fuzz.calibrate(COLOUR, RECORDED["mirror"], RECORDED, build=an_oracle(wrong, poisons))

    def test_an_oracle_that_answers_everything_is_trusted_throughout(self) -> None:
        found = self.reading()

        self.assertTrue(all(one.answered and one.kept_up for one in found.values()))

    def test_a_command_it_answers_wrongly_is_reported(self) -> None:
        found = self.reading(wrong=(fuzz.TILE,))

        self.assertFalse(found["tile"].answered)

    def test_a_command_it_answers_wrongly_does_not_condemn_the_others(self) -> None:
        found = self.reading(wrong=(fuzz.TILE,))

        self.assertTrue(found["mirror"].answered)

    def test_every_sampled_command_gets_a_reading(self) -> None:
        found = self.reading()

        self.assertEqual(sorted(found), sorted(RECORDED))

    def test_a_command_that_answers_and_then_breaks_the_next_one_is_caught(self) -> None:
        found = self.reading(poisons=(fuzz.SYNC,))

        self.assertEqual((found["sync"].answered, found["sync"].kept_up), (True, False))

    def test_such_a_command_is_not_mistaken_for_one_that_answers_wrongly(self) -> None:
        found = self.reading(poisons=(fuzz.SYNC,))

        self.assertTrue(found["mirror"].kept_up)

    def test_a_recording_that_never_set_a_colour_is_still_calibrated(self) -> None:
        found = fuzz.calibrate(None, RECORDED["mirror"], RECORDED, build=an_oracle())

        self.assertTrue(found["mirror"].answered)


class OracleTest(unittest.TestCase):
    """Where the calibration gets the cartridge's answers from."""

    def test_transactions_handed_in_are_used_rather_than_a_recording(self) -> None:
        found = fuzz.oracle(transactions=[COLOUR, *RECORDED.values()], build=an_oracle())

        self.assertEqual(sorted(found or {}), sorted([*RECORDED, "transparent"]))

    def test_a_recording_that_is_not_there_leaves_the_oracle_unchecked(self) -> None:
        found = fuzz.oracle(trace=ROOT / "build" / "no-such-trace.bin")

        self.assertIsNone(found)

    def test_a_recording_on_disk_is_read_and_calibrated_against(self) -> None:
        with tempfile.TemporaryDirectory() as where:
            trace = Path(where) / "tiny.bin"
            trace.write_bytes(b"".join(a_recorded_mirror()))

            found = fuzz.oracle(trace=trace, build=an_oracle())

        self.assertEqual(sorted(found or {}), [fuzz.WITNESS])

    def test_a_recording_without_the_witness_leaves_it_unchecked(self) -> None:
        without = [one for name, one in RECORDED.items() if name != fuzz.WITNESS]

        found = fuzz.oracle(transactions=[COLOUR, *without], build=an_oracle())

        self.assertIsNone(found)


class TrustedTest(unittest.TestCase):
    """Turning readings into the commands a run may generate."""

    def readings(self, **verdicts: tuple[bool, bool]) -> dict[str, Any]:
        return {
            name: fuzz.Reading(*verdicts.get(name, (True, True)))
            for name in ("tile", "merge", "mirror", "multiply", "scale", "sync")
        }

    def test_a_sound_oracle_lets_every_command_through(self) -> None:
        found = fuzz.trusted(self.readings())

        self.assertIn(fuzz.TILE, found)

    def test_a_command_answered_wrongly_is_kept_out(self) -> None:
        found = fuzz.trusted(self.readings(tile=(False, False)))

        self.assertNotIn(fuzz.TILE, found)

    def test_a_command_that_breaks_the_next_one_is_kept_out(self) -> None:
        found = fuzz.trusted(self.readings(sync=(True, False)))

        self.assertNotIn(fuzz.SYNC, found)

    def test_an_unrecognised_byte_goes_out_with_the_sync_it_is_treated_as(self) -> None:
        found = fuzz.trusted(self.readings(sync=(True, False)))

        self.assertNotIn(fuzz.UNKNOWN, found)

    def test_an_unrecognised_byte_stays_while_the_sync_does(self) -> None:
        found = fuzz.trusted(self.readings())

        self.assertIn(fuzz.UNKNOWN, found)

    def test_a_command_the_trace_never_carried_is_not_generated(self) -> None:
        found = fuzz.trusted({name: fuzz.Reading(True, True) for name in ("mirror",)})

        self.assertEqual(found, (fuzz.MIRROR,))


class UncheckedTest(unittest.TestCase):
    """What happens when the oracle cannot be checked at all."""

    def test_a_run_with_no_recording_refuses_rather_than_reporting(self) -> None:
        said: list[str] = []

        code = fuzz.main(
            ["1", "20"],
            refuses=lambda: None,
            assemble=lambda *_: b"skeleton",
            run_batch=lambda *_: (b"script", a_batch()),
            generate=lambda *_args: generated(1, 20),
            say=said.append,
            clock=int,
            checked=lambda: None,
        )

        self.assertEqual(code, 2)
        self.assertIn("unchecked", " ".join(said))

    def test_a_command_the_oracle_fails_is_named_and_left_out(self) -> None:
        said: list[str] = []
        asked: list[Any] = []

        fuzz.main(
            ["1", "20"],
            refuses=lambda: None,
            assemble=lambda *_: b"skeleton",
            run_batch=lambda *_: (b"script", a_batch()),
            generate=_recording_generate(asked, generated),
            say=said.append,
            clock=int,
            checked=lambda: {
                "tile": fuzz.Reading(False, False),
                "mirror": fuzz.Reading(True, True),
            },
        )

        self.assertIn("tile", " ".join(said))
        self.assertNotIn(fuzz.TILE, asked[0][2])

    def test_an_oracle_wrong_about_everything_leaves_nothing_to_run(self) -> None:
        said: list[str] = []

        code = fuzz.main(
            ["1", "20"],
            refuses=lambda: None,
            assemble=lambda *_: b"skeleton",
            run_batch=lambda *_: (b"script", a_batch()),
            generate=lambda *_args: generated(1, 20),
            say=said.append,
            clock=int,
            checked=lambda: {"tile": fuzz.Reading(False, False)},
        )

        self.assertEqual(code, 2)

    def test_a_command_named_on_the_line_that_the_oracle_fails_is_dropped(self) -> None:
        asked: list[Any] = []

        fuzz.main(
            ["1", "20", "0x01", "0x06"],
            refuses=lambda: None,
            assemble=lambda *_: b"skeleton",
            run_batch=lambda *_: (b"script", a_batch()),
            generate=_recording_generate(asked, generated),
            say=lambda _l: None,
            clock=int,
            checked=lambda: {
                "tile": fuzz.Reading(False, False),
                "mirror": fuzz.Reading(True, True),
            },
        )

        self.assertEqual(asked[0][2], [fuzz.MIRROR])


if __name__ == "__main__":
    unittest.main(verbosity=2)
