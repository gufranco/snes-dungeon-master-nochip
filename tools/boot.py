"""Whether the finished cartridge runs, and runs without a coprocessor.

Every other check here asks whether a routine answers correctly. None of them
asks whether the cartridge that ships still wants the chip, and that turns out
to be the one failure the screen cannot show. An image with the replacement
assembled into it and the accesses not redirected boots, plays and looks
perfect, because an emulator reads a header still declaring a DSP-2, provides
one and serves every request itself.

So this reads what the emulator says rather than what it draws. Four things have
to hold: the header declares no coprocessor, nothing asked one for anything, the
run reached the frame it was sent to, and the screen ended up lit. The last is
there because the other three all pass on an image that boots to a black screen,
which is what the first wrong placement of the state block produced.
"""

import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

EMULATOR = "dungeon-master-nochip/emu:dev"

DEFAULT_CARTRIDGE = ROOT / "build" / "Dungeon Master (USA) (nochip).sfc"

DEFAULT_FRAMES = 8000

SCRIPT = "show.script"
"""The input the run is driven with, which walks past the title into the dungeon."""

DARK = 1.0
"""Below this the screen never lit, whatever else the run reported."""

NUMBERS = re.compile(r"(\w+)=(-?\d+(?:\.\d+)?)")


def read(output: str) -> dict[str, float]:
    """Every number the emulator printed about the run, by the name it gave it."""
    found: dict[str, float] = {}
    for line in output.splitlines():
        if not line.startswith(("ROM title=", "RESULT ")):
            continue
        for name, value in NUMBERS.findall(line):
            found[name] = float(value) if "." in value else int(value)
    return found if "delivered" in found else {}


def faults(numbers: dict[str, float], frames: int) -> list[str]:
    """Every way this run failed to be a cartridge that needs no chip."""
    if not numbers:
        return ["the emulator said nothing this could read"]

    found: list[str] = []
    if numbers.get("dsp"):
        found.append(f"the header declares coprocessor {numbers['dsp']:.0f}")
    if numbers.get("dspevents"):
        found.append(f"a chip was asked for something {numbers['dspevents']:,.0f} times")
    if numbers.get("delivered", 0) < frames:
        found.append(f"the run stopped at {numbers.get('delivered', 0):,.0f} of {frames:,}")
    if numbers.get("brightness", 0.0) < DARK:
        found.append("the screen stayed dark for the whole run")
    return found


def run_command(work: Path, cartridge: str, frames: int) -> list[str]:
    """What running the cartridge shells out to.

    The directory is resolved because a relative one is not a directory to
    Docker, it is the name of a volume. Asked for a volume nobody created it
    makes an empty one, mounts that, and the emulator reports it cannot read a
    cartridge that is plainly there.
    """
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "-e",
        f"DMSCRIPT={SCRIPT}",
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
    """One run of the finished cartridge, and what the emulator made of it."""
    cartridge = DEFAULT_CARTRIDGE if len(argv) < 2 else Path(argv[1])
    frames = DEFAULT_FRAMES if len(argv) < 3 else int(argv[2])

    if not cartridge.exists():
        say(f"  no cartridge at {cartridge}; build it first with cartridge.py")
        return 2

    finished = execute(run_command(cartridge.parent, cartridge.name, frames))
    if finished.returncode:
        say(f"  the emulator did not run: {finished.stderr or finished.stdout}")
        return 1

    numbers = read(finished.stdout or "")
    found = faults(numbers, frames)
    for line in found:
        say(f"  {line}")
    if found:
        return 1

    say(
        f"  {frames:,} frames, no coprocessor declared, nothing asked one for anything, "
        f"screen at {numbers['brightness']:.1f}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
