import importlib.util
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _load_beside(name: str) -> Any:
    where = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tour = _load_beside("tour")

EMULATOR = "snes-dungeon-master-nochip/emu:dev"

DEFAULT_CARTRIDGE = ROOT / "build" / "Dungeon Master (USA) (nochip).sfc"

DEFAULT_FRAMES = 8000

SCRIPT = "boot.script"

DARK = 1.0

NUMBERS = re.compile(r"(\w+)=(-?\d+(?:\.\d+)?)")


def read(output: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for line in output.splitlines():
        if not line.startswith(("ROM title=", "RESULT ")):
            continue
        for name, value in NUMBERS.findall(line):
            found[name] = float(value) if "." in value else int(value)
    return found if "delivered" in found else {}


def faults(numbers: dict[str, float], frames: int) -> list[str]:
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
    cartridge = DEFAULT_CARTRIDGE if len(argv) < 2 else Path(argv[1])
    frames = DEFAULT_FRAMES if len(argv) < 3 else int(argv[2])

    if not cartridge.exists():
        say(f"  no cartridge at {cartridge}; build it first with cartridge.py")
        return 2

    (cartridge.parent / SCRIPT).write_text(tour.steady(frames))
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
