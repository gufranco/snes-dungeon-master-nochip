import random
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))

import hardware  # noqa: E402
import script  # noqa: E402

COLOUR_COMMAND = 0x03
MERGE_COMMAND = 0x05

SAFE_LENGTH = 80

SEED = 41


class Case(NamedTuple):
    colour: int
    length: int
    first: bytes
    second: bytes


def expected(colour: int, first: bytes, second: bytes) -> bytes:
    wanted = colour & 0x0F
    return bytes(
        ((one & 0xF0) if (two >> 4) == wanted else (two & 0xF0))
        | ((one & 0x0F) if (two & 0x0F) == wanted else (two & 0x0F))
        for one, two in zip(first, second, strict=True)
    )


def cases(per_length: int) -> list[Case]:
    picked = random.Random(SEED)
    out: list[Case] = []
    for length in range(1, SAFE_LENGTH + 1):
        for _ in range(per_length):
            out.append(
                Case(
                    picked.randrange(16),
                    length,
                    bytes(picked.randrange(256) for _ in range(length)),
                    bytes(picked.randrange(256) for _ in range(length)),
                )
            )
    return out


def runs_for(pairs: Any, answer: Callable[[Case], bytes]) -> list[Any]:
    out: list[Any] = []
    for one in pairs:
        out.append(
            (
                0,
                bytes([COLOUR_COMMAND, one.colour, MERGE_COMMAND, one.length])
                + one.first
                + one.second,
            )
        )
        out.append((1, answer(one)))
    return out


def answer_from(build_chip: Callable[[], Any], one: Case) -> bytes:
    part = build_chip()
    part.write(COLOUR_COMMAND)
    part.write(one.colour)
    part.write(MERGE_COMMAND)
    part.write(one.length)
    for byte in one.first + one.second:
        part.write(byte)
    return bytes(hardware.answer(part) for _ in range(one.length))


def _default_chip(load: Callable[[str], Any] | None = None) -> Any:
    sys.path.insert(0, str(ROOT))
    import hardware

    return (hardware.load if load is None else load)("snesdsp").Chip("dsp2")


def _default_answer_for(build_chip: Callable[[], Any] | None = None) -> Any:
    build = _default_chip if build_chip is None else build_chip
    build()
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
        return [
            f"  {pairs} merges to length {SAFE_LENGTH}, {compared} bytes compared, {wrong} wrong"
        ]
    return [f"  {pairs} merges to length {SAFE_LENGTH}, {compared} bytes compared, none wrong"]


def main(
    argv: tuple[str, ...] | list[str] = (),
    answer_for: Callable[[], Callable[[Case], bytes]] = _default_answer_for,
    walk: Callable[[Any], tuple[int, int, int]] = _default_walk,
    say: Callable[[str], None] = print,
) -> int:
    per_length = int(argv[0]) if argv else 3
    try:
        answer = answer_for()
    except Exception as trouble:
        say(f"  the part had nothing to run here, so this check did not run: {trouble}")
        return 1

    pairs = cases(per_length)
    drifted = [one for one in pairs if answer(one) != expected(one.colour, one.first, one.second)]
    if drifted:
        say(f"  the rule written down here no longer matches the part, on {len(drifted)} cases")
        say(f"  first is a run of {drifted[0].length} at colour {drifted[0].colour:X}")
        return 1

    _, compared, wrong = walk(runs_for(pairs, answer))
    for line in report(len(pairs), compared, wrong):
        say(line)
    return 1 if wrong else 0


script.entry(__name__, main, sys.argv[1:])
