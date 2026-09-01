"""The image the measurements run against, and whether it is the current one.

Three things read an assembled image and its label table: the cost report and the
two sets of checks that drive a path no recording reaches. Each of them used to
be handed one by whoever remembered to run the assembler by hand, with the right
flags, in the right container. That is four commands to type and one of them is
easy to leave out, which is how a run came to be measured against a table
describing where the code used to be.

So the location is stated once, the build is one call, and staleness is a
question anything can ask. Stale means older than any file the assembler reads,
which is the whole of the assembly directory: a header changed there moves every
routine after it, and a table that predates the move sends a measurement into
the stack.
"""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build  # noqa: E402

ASSEMBLY = ROOT / "asm" / "nochip.asm"

IMAGE = ROOT / "asm" / "dm-sym.sfc"
"""The retail image with the routines and the stubs assembled into its filler.

The accesses are not redirected in it, which is what the measurements want: they
call the routines directly. cartridge.py produces the one somebody plays.
"""

SYMBOLS = IMAGE.with_suffix(".sym")

DUMP = ROOT / "roms" / "dungeon-master-usa.sfc"


def sources() -> list[Path]:
    """Every file the assembler reads, so a change to any of them counts."""
    return sorted(one for one in ASSEMBLY.parent.glob("*.asm") if one.is_file())


def stale() -> str | None:
    """Why the image cannot be measured against, or nothing when it can."""
    if not IMAGE.exists():
        return f"{IMAGE.name} has not been built"
    if not SYMBOLS.exists():
        return f"{SYMBOLS.name} is missing, so every routine would be entered by guess"

    built = IMAGE.stat().st_mtime
    if SYMBOLS.stat().st_mtime < built:
        return f"{SYMBOLS.name} is older than {IMAGE.name}; assemble them together"

    newer = [one.name for one in sources() if one.stat().st_mtime > built]
    if newer:
        return f"{IMAGE.name} predates {', '.join(newer)}"
    return None


def assemble(
    dump: Path | str = DUMP,
    say: Callable[[str], None] = print,
    run: Any = None,
) -> int:
    """The image and its label table, built together by the pinned assembler."""
    run = build.main if run is None else run
    if not Path(dump).exists():
        say(f"  no dump at {dump}; the builder supplies their own")
        return 2
    return int(run(["build.py", str(ASSEMBLY), str(dump), IMAGE.name], say=say))


def ready(
    dump: Path | str = DUMP,
    say: Callable[[str], None] = print,
    run: Any = None,
) -> int:
    """Assemble only when what is on disk cannot be measured against."""
    reason = stale()
    if reason is None:
        return 0
    say(f"  {reason}")
    return assemble(dump, say, run)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(ready())
