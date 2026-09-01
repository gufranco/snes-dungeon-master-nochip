"""The finished cartridge, from a retail dump.

Producing one is two steps that have to happen in order, and only the first had
a command. The assembler places the routines and the stubs in filler no tour
ever read. Then every access the cartridge makes to the chip is pointed at them
and the header stops declaring a coprocessor.

An image that has had only the first step done looks like a working build. It
carries the whole replacement, it boots, and it plays, because the emulator sees
a header still declaring a DSP-2 and provides one. The tell is in what the
emulator reports rather than in what the screen shows: `dsp=2` and twenty two
million chip events on a run that was supposed to have none.

So the two checks at the end are not ceremony. `patch.residue` says whether any
access still goes to bank $3F, and the image model says whether any mirror of
the header still declares a coprocessor. Either one non-empty and this refuses
to hand over the file, because a cartridge that quietly still wants the chip is
the one failure this project exists to prevent.
"""

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
    """Where the assembler writes the label table for an image.

    It is emitted on a pass of its own, so a build that does not ask for it
    leaves whatever the last one wrote. Read against a table that stale, every
    routine is entered at the address it used to be at, and the first one runs
    off into the stack and reports that it never returned.
    """
    return Path(image).with_suffix(".sym")


def finish(image: bytes | bytearray, symbols_text: str) -> bytes:
    """The assembled image with every access redirected and the chip undeclared."""
    symbols = patch.resolve(patch.read_symbols(symbols_text))
    declared: bytes = romimage.declare_rom_only(patch.apply(image, symbols))
    return declared


def unfinished(image: bytes | bytearray) -> list[str]:
    """Every way this image would still ask for a chip that is not there."""
    left = [
        f"{count} {kind} accesses still go to the chip"
        for kind, count in patch.residue(image).items()
    ]
    if romimage.needs_rewrite(image):
        return [*left, "the header still declares a coprocessor or the wrong size"]
    return left


ASSEMBLY = build.ASM_DIR / "nochip.asm"
"""The source that places the routines and the stubs in the image."""


def assemble(argv: list[str], say: Callable[[str], None] = print) -> int:
    """The assembler, run through the pinned container."""
    return build.main(argv, say=say)


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    assemble: Any = assemble,
    left: Any = unfinished,
    staged: Path | str | None = None,
) -> int:
    """A retail dump in, a cartridge that needs no coprocessor out."""
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
