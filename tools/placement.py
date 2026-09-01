"""Whether the game still leaves alone the work RAM the state block sits in.

The chip kept its command and parameter state inside itself. The replacement has
to keep it somewhere the game does not use, and where that is was found by
measurement rather than by reading a map nobody wrote: run the cartridge,
compare the whole of work RAM against the previous frame after every frame, and
take the longest stretch nothing ever changed.

That is a claim about the game, and a claim of that shape is only as good as the
inputs it was made under. This is the check that lets another input be tried.
It runs the retail cartridge, asks the emulator for the same map, and fails if
anything wrote inside the region the block claims.

The instrument matters as much as the result. An earlier one watched byte
accesses only. This game moves work RAM by DMA, which that path does not see, so
it reported 37,245 bytes free, the block went on top of a live table, and the
converted image drew a blank screen. The map read here is the frame by frame
comparison, which sees a write whatever made it.
"""

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _load_beside(name: str) -> Any:
    """A module that sits next to this one, loaded the way the tools load each other."""
    where = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tour = _load_beside("tour")

EMULATOR = "dungeon-master-nochip/emu:dev"

MAP = "wram-map.bin"

SCRIPT = "placement.script"

DEFAULT_CARTRIDGE = ROOT / "roms" / "dungeon-master-usa.sfc"

DEFAULT_FRAMES = 19000


def define(name: str, source: Path) -> int:
    """One of the assembler's `!NAME = $hex` defines, as a number.

    The addresses are read from the assembly rather than repeated here, because
    two declarations of one address drift and the drift is silent: this would go
    on reporting a region clear while the block had moved somewhere else.
    """
    for line in source.read_text().splitlines():
        head, _, tail = line.partition("=")
        if head.strip() != name:
            continue
        return int(tail.strip().split()[0].lstrip("$"), 16)
    raise AssertionError(f"{name} is not defined in {source.name}")


STATE = define("!STATE", ROOT / "asm" / "dsp2-state.asm") & 0xFFFF
STATE_END = define("!STATE_END", ROOT / "asm" / "dsp2-state.asm") & 0xFFFF


def taken(touched: bytes) -> list[int]:
    """Every byte inside the block's region that the game wrote or read."""
    return [at for at in range(STATE, STATE_END) if touched[at]]


def free(touched: bytes) -> list[tuple[int, int]]:
    """Each stretch the game left alone, longest first."""
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
    """What the run found, in one line."""
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


def run_command(work: Path, cartridge: str, frames: int) -> list[str]:
    """What mapping one run shells out to."""
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "-e",
        f"DMSCRIPT={SCRIPT}",
        "-e",
        f"DMWRAM={MAP}",
        "-v",
        f"{work.resolve()}:/work",
        EMULATOR,
        cartridge,
        str(frames),
    ]


def _shell_out(args: list[str]) -> Any:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    execute: Any = _shell_out,
) -> int:
    """One mapped run of the retail cartridge, and whether the block's region survived it."""
    cartridge = DEFAULT_CARTRIDGE if len(argv) < 2 else Path(argv[1])
    frames = DEFAULT_FRAMES if len(argv) < 3 else int(argv[2])

    if not cartridge.exists():
        say(f"  no dump at {cartridge}; the builder supplies their own")
        return 2

    work = cartridge.parent
    (work / SCRIPT).write_text(tour.steady(frames))

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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
