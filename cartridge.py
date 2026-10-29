import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build
import hardware
import patch
import version

romimage = hardware.load("romimage")

DIST = Path(__file__).resolve().parent / "dist"
HEADED_SUFFIX = ".smc"
EMULATOR = "emulator"
SUPER_EVERDRIVE = "supereverdrive"
SD2SNES = "sd2snes"
FXPAK = "fxpak"
GAME_DOCTOR = "gamedoctor"
DEVICES = (EMULATOR, SUPER_EVERDRIVE, SD2SNES, FXPAK, GAME_DOCTOR)


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


def assemble(
    argv: list[str],
    say: Callable[[str], None] = print,
    builder: Callable[..., int] = build.main,
) -> int:
    try:
        return builder(argv, say=say)
    except build.ToolchainMissing as absent:
        say(f"  {absent}")
        return 1


def output_name(source: Path | str, release: str | None = None) -> str:
    found: str = version.stamped(f"{Path(source).stem}-nochip", release)
    return found


def release_folder(release: str | None = None) -> str:
    found: str = version.stamped("", release)
    return found.removesuffix(version.EXTENSION).lstrip("-")


def forms_of(name: str, final: bytes) -> list[tuple[str, bytes]]:
    headed = Path(name).with_suffix(HEADED_SUFFIX).name
    return [
        (f"{EMULATOR}/{name}", final),
        (f"{SUPER_EVERDRIVE}/{name}", final),
        (f"{SD2SNES}/{name}", final),
        (f"{FXPAK}/{name}", final),
        (f"{GAME_DOCTOR}/{headed}", romimage.copier.for_game_doctor(final)),
    ]


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    assemble: Any = assemble,
    left: Any = unfinished,
    staged: Path | str | None = None,
) -> int:
    if len(argv) < 2:
        say("usage: cartridge.py <source-rom> [<destination>]")
        return 2

    source = Path(argv[1])
    destination = (Path(argv[2]) if len(argv) > 2 else DIST) / release_folder()
    if not source.exists():
        say(f"  no dump at {source}")
        return 2

    name = output_name(source)
    code = int(assemble(["build.py", str(ASSEMBLY), str(source), name], say=say))
    if code:
        say("  the assembler did not finish, so nothing was patched")
        return code

    where = build.staged_path(ASSEMBLY, name) if staged is None else Path(staged)
    final = finish(where.read_bytes(), symbols_beside(where).read_text())

    remaining = left(final)
    if remaining:
        for line in remaining:
            say(f"  {line}")
        return 1

    for relative, written in forms_of(name, final):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(written)
        say(f"[done] {target} ({len(written):,} bytes)")
    return 0


script.entry(__name__, main, sys.argv)
