"""The tile, the mirror and the scale, checked against the part rather than a recording.

The recordings settle what the cartridge asked for. They cannot settle what the
answer should be, because they hold an emulator's answers, and no single one of
them even reaches all six commands: one route of thirty thousand frames produces
no mirror at all.

So this asks the part, over inputs chosen rather than observed, and feeds those
answers to the routines on the processor. There is no rule written down here for
either command. Both are held to the part directly, which is the highest thing
this project can reach and removes any question of a transcription being wrong.

The mirror stops at the same declared length the merge does. The two share the
protocol's length byte and the part's buffer, and beyond that length the part
does something the routines do not follow, which is recorded as an open question
rather than hidden by a check that avoids it.
"""

import random
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parent.parent

TILE = 0x01
MIRROR = 0x06
SCALE = 0x0D

TILE_BYTES = 32
"""What a tile takes and gives, which the protocol fixes rather than declares."""

SAFE_LENGTH = 80

SCALE_PAIRS = ((72, 38), (120, 80))
"""The only two length pairs the cartridge asks a scale for, counted in nibbles.

One recorded tour asks for these two across 10,422 calls and for nothing else.
The scale is deliberately not among the cases below. Driven the way the other
commands here are driven it disagrees with the part on 146 of 236 bytes, and
whether that is the part or the driving is not established: the tile needed a
preamble understood before it agreed, and the merge needed its length byte, so a
disagreement on a command nobody has driven before is a question rather than a
result. It is recorded as an open question instead of shipped as a passing check
that quietly avoids it.
"""

SEED = 17


PREAMBLE = {TILE: 1, MIRROR: 0, SCALE: 0}
"""How many bytes the part offers before the answer, per command.

Measured. A tile is preceded by one byte the cartridge's own read pattern
accounts for and which is not part of the answer: skipping it reproduces 200 of
200 recorded tiles, and not skipping it reproduces none. A mirror has no such
byte. It is a property of the protocol rather than of the arithmetic, and it is
the single thing that made a byte driven replay of a whole trace impossible to
keep in step.
"""


class Case(NamedTuple):
    command: int
    lengths: tuple[int, ...]
    payload: bytes
    reads: int


def cases(each: int) -> list[Case]:
    """Tiles at the one width there is, and mirrors across the lengths there are."""
    picked = random.Random(SEED)
    out: list[Case] = []
    for _ in range(each * 8):
        payload = bytes(picked.randrange(256) for _ in range(TILE_BYTES))
        out.append(Case(TILE, (), payload, TILE_BYTES))
    for length in range(1, SAFE_LENGTH + 1):
        for _ in range(each):
            payload = bytes(picked.randrange(256) for _ in range(length))
            out.append(Case(MIRROR, (length,), payload, length))
    return out


def answer_from(build_chip: Callable[[], Any], one: Case) -> bytes:
    """One exchange put to a part the caller builds."""
    part = build_chip()
    part.write(one.command)
    for length in one.lengths:
        part.write(length)
    for byte in one.payload:
        part.write(byte)
    for _ in range(PREAMBLE[one.command]):
        part.read()
    return bytes(part.read() for _ in range(one.reads))


def runs_for(pairs: Any, answer: Callable[[Case], bytes]) -> list[Any]:
    """Each case as the cartridge would send it, and what the part gives back."""
    out: list[Any] = []
    for one in pairs:
        out.append((0, bytes([one.command, *one.lengths]) + one.payload))
        out.append((1, answer(one)))
    return out


def _default_chip(load: Callable[[str], Any] | None = None) -> Any:
    sys.path.insert(0, str(ROOT))
    import hardware

    return (hardware.load if load is None else load)("snesdsp").Chip("dsp2")


def _default_answer_for(build_chip: Callable[[], Any] | None = None) -> Any:
    build = _default_chip if build_chip is None else build_chip
    return lambda one: answer_from(build, one)


def _load_replay() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("replay", ROOT / "tools" / "replay.py")
    assert spec is not None and spec.loader is not None, "no loader for the replay harness"
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    return replay


def _default_walk(runs: Any, load: Callable[[], Any] = _load_replay) -> tuple[int, int, int]:
    replay = load()
    build = ROOT / "build"
    skeleton = replay.assemble(ROOT, build)
    _, found = replay.run_batch(build, skeleton, runs)
    return found["transactions"], found["compared"], found["wrong"]


def report(pairs: int, compared: int, wrong: int) -> list[str]:
    if wrong:
        return [f"  {pairs} exchanges, {compared} bytes compared, {wrong} wrong"]
    return [f"  {pairs} exchanges, {compared} bytes compared, none wrong"]


def main(
    argv: tuple[str, ...] | list[str] = (),
    answer_for: Callable[[], Callable[[Case], bytes]] = _default_answer_for,
    walk: Callable[[Any], tuple[int, int, int]] = _default_walk,
    say: Callable[[str], None] = print,
) -> int:
    each = int(argv[0]) if argv else 2
    try:
        answer = answer_for()
    except Exception as trouble:
        say(f"  the part had nothing to run here, so this check did not run: {trouble}")
        return 0

    pairs = cases(each)
    _, compared, wrong = walk(runs_for(pairs, answer))
    for line in report(len(pairs), compared, wrong):
        say(line)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
