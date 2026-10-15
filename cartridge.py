import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build
import hardware
import patch

romimage = hardware.load("romimage")


def symbols_beside(image: Path | str) -> Path:
    return Path(image).with_suffix(".sym")


def finish(image: bytes | bytearray, symbols_text: str) -> bytes:
    symbols = patch.resolve(patch.read_symbols(symbols_text))
    declared: bytes = romimage.declare_rom_only(patch.apply(image, symbols))
    return declared


def unfinished(image: bytes | bytearray) -> list[str]:
    left = [
        f"{count} {kind} accesses still go to the chip"
        for kind, count in patch.residue(image).items()
    ]
    if romimage.needs_rewrite(image):
        return [*left, "the header still declares a coprocessor or the wrong size"]
    return left


ASSEMBLY = build.ASM_DIR / "nochip.asm"


def assemble(argv: list[str], say: Callable[[str], None] = print) -> int:
    return build.main(argv, say=say)


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    assemble: Any = assemble,
    left: Any = unfinished,
    staged: Path | str | None = None,
) -> int:
    if len(argv) < 3:
        say("usage: cartridge.py <source-rom> <output-rom>")
        return 2

    source, output = Path(argv[1]), Path(argv[2])
    if not source.exists():
        say(f"  no dump at {source}")
        return 2

    code = int(assemble(["build.py", str(ASSEMBLY), str(source), output.name], say=say))
    if code:
        say("  the assembler did not finish, so nothing was patched")
        return code

    where = build.staged_path(ASSEMBLY, output.name) if staged is None else Path(staged)
    final = finish(where.read_bytes(), symbols_beside(where).read_text())

    remaining = left(final)
    if remaining:
        for line in remaining:
            say(f"  {line}")
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(final)
    say(f"[done] {output} ({len(final):,} bytes)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
