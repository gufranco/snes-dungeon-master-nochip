import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cost = load_module("cost", ROOT / "tools" / "cost.py")

IMAGE = ROOT / "asm" / "dm-sym.sfc"

SYMBOLS = IMAGE.with_suffix(".sym")

SCALE = 0x0D

PAIRS = ((72, 38), (120, 80))
"""The two length pairs one recorded tour asks for, in 10,422 scale calls."""


def payload_for(lengths: tuple[int, int]) -> bytes:
    """A payload of the size those declared lengths imply, which count nibbles."""
    return bytes((0x11 * (at % 15 + 1)) & 0xFF for at in range((lengths[0] + 1) >> 1))


def produced_for(lengths: tuple[int, int]) -> int:
    """How many bytes a scale with those lengths hands back."""
    return (lengths[1] + 1) >> 1


"""That the held resampling step is dropped when the lengths change.

A scale derives its step by dividing, and the cartridge asks for the same answer
over and over: one tour makes 10,422 calls with two distinct length pairs between
them. The step is held and reused, so what has to be checked is not the division,
which the recordings exercise, but the moment the held answer stops applying.

These need the assembled image, which needs the dump, so on a machine without one
they report as skipped.
"""


@unittest.skipUnless(
    IMAGE.exists() and SYMBOLS.exists(),
    "the assembled image is built from a dump the builder supplies",
)
class ScaleStepTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.names = cost.symbols(SYMBOLS.read_text())
        self.rom = IMAGE.read_bytes()

    def fresh(self) -> Any:
        cpu, memory = cost.machine(self.rom)
        cost.enter(cpu, self.names["dsp_init"])
        return cpu, memory

    def scaled(self, machine: Any, lengths: tuple[int, int]) -> bytes:
        cpu, memory = machine
        cost.measure(
            cpu,
            memory,
            self.names,
            SCALE,
            lengths,
            payload_for(lengths),
            produced_for(lengths),
        )
        answered: bytes = cost.produced(memory, produced_for(lengths))
        return answered

    def alone(self, lengths: tuple[int, int]) -> bytes:
        """What a machine that has scaled nothing else answers for those lengths."""
        return self.scaled(self.fresh(), lengths)

    def test_each_pair_answers_the_same_alone_as_it_does_first(self) -> None:
        machine = self.fresh()

        self.assertEqual(self.scaled(machine, PAIRS[0]), self.alone(PAIRS[0]))

    def test_a_second_pair_is_not_answered_with_the_first_pairs_step(self) -> None:
        machine = self.fresh()
        self.scaled(machine, PAIRS[0])

        self.assertEqual(self.scaled(machine, PAIRS[1]), self.alone(PAIRS[1]))

    def test_and_the_first_pair_again_is_not_answered_with_the_second_pairs(self) -> None:
        machine = self.fresh()
        self.scaled(machine, PAIRS[0])
        self.scaled(machine, PAIRS[1])

        self.assertEqual(self.scaled(machine, PAIRS[0]), self.alone(PAIRS[0]))

    def test_repeating_one_pair_answers_the_same_every_time(self) -> None:
        machine = self.fresh()
        expected = self.alone(PAIRS[0])

        for _ in range(4):
            self.assertEqual(self.scaled(machine, PAIRS[0]), expected)

    def test_the_two_pairs_do_not_answer_the_same_thing(self) -> None:
        self.assertNotEqual(self.alone(PAIRS[0]), self.alone(PAIRS[1])[: produced_for(PAIRS[0])])


if __name__ == "__main__":
    unittest.main()
