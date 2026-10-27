import random
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))
import hardware  # noqa: E402

TILE = 0x01
MIRROR = 0x06
SCALE = 0x0D

TILE_BYTES = 32

SAFE_LENGTH = 80

SCALE_PAIRS = ((72, 38), (120, 80))

SEED = 17


PREAMBLE = {TILE: 1, MIRROR: 0, SCALE: 0}


class Case(NamedTuple):
    command: int
    lengths: tuple[int, ...]
    payload: bytes
    reads: int


def cases(each: int) -> list[Case]:
    picked = random.Random(SEED)
    out: list[Case] = []
    for _ in range(each * 8):
        payload = bytes(picked.randrange(256) for _ in range(TILE_BYTES))
        out.append(Case(TILE, (), payload, TILE_BYTES))
    for length in range(1, SAFE_LENGTH + 1):
        for _ in range(each):
            payload = bytes(picked.randrange(256) for _ in range(length))
            out.append(Case(MIRROR, (length,), payload, length))
    for lengths in SCALE_PAIRS:
        for _ in range(each * 4):
            payload = bytes(picked.randrange(256) for _ in range((lengths[0] + 1) >> 1))
            out.append(Case(SCALE, lengths, payload, (lengths[1] + 1) >> 1))
    return out


def answer_from(build_chip: Callable[[], Any], one: Case) -> bytes:
    part = build_chip()
    part.write(one.command)
    for length in one.lengths:
        part.write(length)
    for byte in one.payload:
        part.write(byte)
    for _ in range(PREAMBLE[one.command]):
        hardware.answer(part)
    return bytes(hardware.answer(part) for _ in range(one.reads))


def runs_for(pairs: Any, answer: Callable[[Case], bytes]) -> list[Any]:
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
        return 1

    pairs = cases(each)
    _, compared, wrong = walk(runs_for(pairs, answer))
    for line in report(len(pairs), compared, wrong):
        say(line)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
