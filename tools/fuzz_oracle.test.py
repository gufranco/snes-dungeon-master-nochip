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
    return (
        struct.pack("<II", 0, 294912)
        + struct.pack("<HH", 0, 0)
        + bytes([kind, byte])
        + bytes([0x00, 0x00, DSP_BANK, 0x00, 126, DSP_BANK, 0x00, 0x00])
        + bytes([0x00, 0x30])
        + bytes([0xA9, 0x00, 0x00, 0x00])
    )


def a_recorded_mirror() -> list[bytes]:
    written = [a_record(KIND_WRITE, byte) for byte in (fuzz.MIRROR, 0x02, 0x12, 0x34)]
    return [*written, *(a_record(KIND_READ, byte) for byte in (0x43, 0x21))]


class Oracle:
    asking = True

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

    def build() -> Any:
        return Oracle(wrong, poisons)

    return build


class SampleTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
