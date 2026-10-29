import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import script  # noqa: E402
import toolchain  # noqa: E402


def _load_beside(name: str) -> Any:
    where = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tour = _load_beside("tour")


MAP = "wram-map.bin"

SCRIPT = "placement.script"

DEFAULT_CARTRIDGE = ROOT / "external" / "roms" / "dungeon-master-usa.sfc"

DEFAULT_FRAMES = 19000


def define(name: str, source: Path) -> int:
    for line in source.read_text().splitlines():
        head, _, tail = line.partition("=")
        if head.strip() != name:
            continue
        return int(tail.strip().split()[0].lstrip("$"), 16)
    raise AssertionError(f"{name} is not defined in {source.name}")


STATE = define("!STATE", ROOT / "asm" / "dsp2-state.asm") & 0xFFFF
STATE_END = define("!STATE_END", ROOT / "asm" / "dsp2-state.asm") & 0xFFFF


def taken(touched: bytes) -> list[int]:
    return [at for at in range(STATE, STATE_END) if touched[at]]


def free(touched: bytes) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for at in range(len(touched)):
        if not touched[at]:
            start = at if start is None else start
        elif start is not None:
            runs.append((start, at - start))
            start = None
    if start is not None:
        runs.append((start, len(touched) - start))
    return sorted(runs, key=lambda one: -one[1])


def summary(used: list[int], runs: list[tuple[int, int]], frames: int) -> str:
    longest = f"${runs[0][0]:05X} for {runs[0][1]:,} bytes" if runs else "none"
    where = f"${STATE:05X} to ${STATE_END - 1:05X}"
    if used:
        return (
            f"  over {frames:,} frames the game wrote inside {where}, first at ${used[0]:05X}"
            f", {len(used):,} bytes in all; longest free stretch {longest}"
        )
    return (
        f"  over {frames:,} frames the game never touched {where}; longest free stretch {longest}"
    )


def route_for(frames: int, seed: int | None) -> str:
    route: str = tour.steady(frames) if seed is None else tour.build(frames, seed)
    return route


def run_command(work: Path, cartridge: str, frames: int) -> list[str]:
    return toolchain.command(
        toolchain.EMULATOR,
        [f"DMSCRIPT={SCRIPT}", f"DMWRAM={MAP}"],
        [cartridge, str(frames)],
        work.resolve(),
    )


def _shell_out(args: list[str]) -> Any:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    execute: Any = _shell_out,
) -> int:
    cartridge = DEFAULT_CARTRIDGE if len(argv) < 2 else Path(argv[1])
    frames = DEFAULT_FRAMES if len(argv) < 3 else int(argv[2])
    seed = None if len(argv) < 4 else int(argv[3])

    if not cartridge.exists():
        say(f"  no dump at {cartridge}; the builder supplies their own")
        return 2

    work = cartridge.parent
    (work / SCRIPT).write_text(route_for(frames, seed))

    finished = execute(run_command(work, cartridge.name, frames))
    if finished.returncode:
        say(f"  the emulator did not run: {finished.stderr or finished.stdout}")
        return 1

    where = work / MAP
    if not where.exists():
        say("  the run left no map of work RAM")
        return 1

    touched = where.read_bytes()
    used = taken(touched)
    say(summary(used, free(touched), frames))
    return 1 if used else 0


script.entry(__name__, main, sys.argv)
