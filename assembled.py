import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build  # noqa: E402

ASSEMBLY = ROOT / "asm" / "nochip.asm"

IMAGE = ROOT / "asm" / "dm-sym.sfc"

SYMBOLS = IMAGE.with_suffix(".sym")

DUMP = ROOT / "roms" / "dungeon-master-usa.sfc"


def sources() -> list[Path]:
    return sorted(one for one in ASSEMBLY.parent.glob("*.asm") if one.is_file())


def stale() -> str | None:
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
    reason = stale()
    if reason is None:
        return 0
    say(f"  {reason}")
    return assemble(dump, say, run)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(ready())
