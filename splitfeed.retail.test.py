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

MERGE = 0x05

SET_TRANSPARENT = 0x03

LENGTH = 8
"""Bytes of background, and of overlay, in the merge these checks drive."""

TRANSPARENT = 0x0A


"""The one path no recording reaches: a payload delivered in more than one move.

Every transfer the cartridge makes carries exactly what the command still wants,
across all four recordings and 4.6 million transactions, so the loop that
handles a payload arriving in pieces has never run outside these checks. That is
what made a field collision in the state block invisible: the overlay pointer
was declared on top of the bank a split transfer re-reads, and only a split
would have shown it.

These need the assembled image, which needs the dump, so on a machine without
one they report as skipped.
"""


@unittest.skipUnless(
    IMAGE.exists() and SYMBOLS.exists(),
    "the assembled image is built from a dump the builder supplies",
)
class SplitFeedTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.names = cost.symbols(SYMBOLS.read_text())
        self.cpu, self.memory = cost.machine(IMAGE.read_bytes())
        cost.enter(self.cpu, self.names["dsp_init"])
        self.payload = bytes(range(0x10, 0x10 + LENGTH * 2))
        self.colour()

    def colour(self) -> None:
        """The transparent colour a merge decides against, set the way the game sets it."""
        cost.measure(
            self.cpu, self.memory, self.names, SET_TRANSPARENT, (), bytes([TRANSPARENT]), 0
        )

    def head(self, command: int, lengths: tuple[int, ...]) -> None:
        for byte in bytes([command]) + bytes(lengths):
            self.cpu.set_acc(byte)
            cost.enter(self.cpu, self.names["dsp_write"])

    def feed(self, payload: bytes, at: int) -> None:
        where = (cost.SOURCE & 0xFFFF) + at
        self.memory.wram[where : where + len(payload)] = payload
        self.cpu.m8 = False
        self.cpu.x8 = False
        self.cpu.a = len(payload) - 1
        self.cpu.x = where
        self.cpu.y = 0x0000
        cost.enter(self.cpu, self.names["dsp_feed_wram"])

    def drain(self, length: int) -> bytes:
        self.cpu.m8 = False
        self.cpu.x8 = False
        self.cpu.a = length - 1
        self.cpu.x = 0x0000
        self.cpu.y = cost.DESTINATION & 0xFFFF
        cost.enter(self.cpu, self.names["dsp_drain_wram"])
        drained: bytes = cost.produced(self.memory, length)
        return drained

    def whole(self) -> bytes:
        self.head(MERGE, (LENGTH,))
        self.feed(self.payload, 0)
        return self.drain(LENGTH)

    def in_pieces(self, first: int) -> bytes:
        self.head(MERGE, (LENGTH,))
        self.feed(self.payload[:first], 0)
        self.feed(self.payload[first:], first)
        return self.drain(LENGTH)

    def test_a_payload_split_in_half_answers_what_one_move_answers(self) -> None:
        expected = self.whole()

        self.assertEqual(self.in_pieces(LENGTH), expected)

    def test_and_split_anywhere_else(self) -> None:
        expected = self.whole()

        for first in (1, 3, LENGTH - 1, LENGTH + 1, LENGTH * 2 - 1):
            with self.subTest(first=first):
                self.assertEqual(self.in_pieces(first), expected)

    def test_a_payload_delivered_one_byte_at_a_time_answers_the_same(self) -> None:
        expected = self.whole()

        self.head(MERGE, (LENGTH,))
        for at, byte in enumerate(self.payload):
            self.feed(bytes([byte]), at)

        self.assertEqual(self.drain(LENGTH), expected)

    def test_one_move_carrying_two_whole_commands_answers_both(self) -> None:
        """The path the layout collision would have broken, and the only one that reaches it.

        A transfer that overruns one command's payload carries on into the next,
        and when that next command collects a payload of its own the loop goes
        back round to the block branch, which re-reads the bank to move from.
        Splitting a payload across two calls does not reach it: each call sets
        that bank again on the way in. One call has to do both.

        What is left to read afterwards is the second merge's answer alone.
        There is one output buffer, and a command that runs spends what the last
        one left in it, which is what the part does.
        """
        expected = self.whole()

        self.head(MERGE, (LENGTH,))
        self.feed(self.payload + bytes([MERGE, LENGTH]) + self.payload, 0)

        self.assertEqual(self.drain(LENGTH), expected)

    def test_a_result_drained_in_pieces_is_the_same_result(self) -> None:
        expected = self.whole()

        self.head(MERGE, (LENGTH,))
        self.feed(self.payload, 0)
        first = self.drain(LENGTH // 2)
        rest = self.drain(LENGTH - LENGTH // 2)

        self.assertEqual(first + rest, expected)


if __name__ == "__main__":
    unittest.main()
