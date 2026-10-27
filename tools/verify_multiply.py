import random
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))
import hardware  # noqa: E402

COMMAND = 0x09

ANSWER_BYTES = 4

SEED = 99

EDGES = (
    (0, 0),
    (0, 6),
    (6, 0),
    (1, 1),
    (2, 3),
    (100, 100),
    (1000, 1000),
    (4095, 4095),
    (32767, 2),
    (0x8000, 0x8000),
    (0x8000, 1),
    (0xFFFF, 0xFFFF),
    (0xFFFF, 2),
    (1, 0xFFFF),
    (0xC000, 0x4000),
    (0x4000, 2),
    (0x3FFF, 2),
)


def signed(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def expected(first: int, second: int) -> tuple[int, int]:
    product = (signed(first) * signed(second)) & 0xFFFFFFFF
    low = (product & 0x7FFF) | ((product & 0x4000) << 1)
    high = (product >> 16) & 0x7FFF
    return low, high


def cases(extra: int) -> list[tuple[int, int]]:
    picked = random.Random(SEED)
    return [*EDGES, *((picked.randrange(0x10000), picked.randrange(0x10000)) for _ in range(extra))]


def runs_for(pairs: Any, answer: Callable[[int, int], bytes]) -> list[Any]:
    out: list[Any] = []
    for first, second in pairs:
        out.append(
            (
                0,
                bytes(
                    [
                        COMMAND,
                        first & 0xFF,
                        (first >> 8) & 0xFF,
                        second & 0xFF,
                        (second >> 8) & 0xFF,
                    ]
                ),
            )
        )
        out.append((1, answer(first, second)))
    return out


def report(pairs: int, compared: int, wrong: int) -> list[str]:
    if wrong:
        return [f"  {pairs} operand pairs, {compared} bytes compared, {wrong} wrong"]
    return [f"  {pairs} operand pairs, {compared} bytes compared, none wrong"]


def answer_from(build_chip: Callable[[], Any], first: int, second: int) -> bytes:
    part = build_chip()
    part.write(COMMAND)
    for value in (first, second):
        part.write(value & 0xFF)
        part.write((value >> 8) & 0xFF)
    return bytes(hardware.answer(part) for _ in range(ANSWER_BYTES))


def _default_chip(load: Callable[[str], Any] | None = None) -> Any:
    sys.path.insert(0, str(ROOT))
    import hardware

    return (hardware.load if load is None else load)("snesdsp").Chip("dsp2")


def _default_answer_for(build_chip: Callable[[], Any] | None = None) -> Any:
    build = _default_chip if build_chip is None else build_chip
    build()
    return lambda first, second: answer_from(build, first, second)


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


def main(
    argv: tuple[str, ...] | list[str] = (),
    answer_for: Callable[[], Callable[[int, int], bytes]] = _default_answer_for,
    walk: Callable[[Any], tuple[int, int, int]] = _default_walk,
    say: Callable[[str], None] = print,
) -> int:
    extra = int(argv[0]) if argv else 120
    try:
        answer = answer_for()
    except Exception as trouble:
        say(f"  the part had nothing to run here, so this check did not run: {trouble}")
        return 1

    pairs = cases(extra)
    drifted = [
        (first, second)
        for first, second in pairs
        if int.from_bytes(answer(first, second), "little")
        != expected(first, second)[0] | (expected(first, second)[1] << 16)
    ]
    if drifted:
        say(f"  the rule written down here no longer matches the part, on {len(drifted)} pairs")
        say(f"  first is {drifted[0][0]} times {drifted[0][1]}")
        return 1

    _, compared, wrong = walk(runs_for(pairs, answer))
    for line in report(len(pairs), compared, wrong):
        say(line)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
