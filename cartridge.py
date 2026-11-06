import hashlib
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import script

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build
import hardware
import patch
import toolchain
import version

ROOT = Path(__file__).resolve().parent


def _load_tool(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


romimage = hardware.load("romimage")
identify = _load_tool("identify")

DIST = ROOT / "dist"
SUMS = "SHA256SUMS"
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


def declared_as(dump: bytes, manifest: Any) -> str | None:
    found = identify.accepted_digests(manifest).get(identify.digests(dump).sha256)
    return None if found is None else str(found["filename"])


def forms_of(name: str, final: bytes) -> list[tuple[str, bytes]]:
    headed = Path(name).with_suffix(HEADED_SUFFIX).name
    return [
        (f"{EMULATOR}/{name}", final),
        (f"{SUPER_EVERDRIVE}/{name}", final),
        (f"{SD2SNES}/{name}", final),
        (f"{FXPAK}/{name}", final),
        (f"{GAME_DOCTOR}/{headed}", romimage.copier.for_game_doctor(final)),
    ]


def sums_line(relative: str, written: bytes) -> str:
    return f"{hashlib.sha256(written).hexdigest()}  {relative}"


def write_forms(destination: Path, name: str, final: bytes, say: Callable[[str], None]) -> None:
    forms = forms_of(name, final)
    for relative, written in forms:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(written)
        say(f"[done] {target} ({len(written):,} bytes)")
    (destination / SUMS).write_text("".join(f"{sums_line(*form)}\n" for form in forms))
    say(f"[done] {destination / SUMS} ({len(forms)} images)")


def named_or_refused(source: Path, manifest: Any, say: Callable[[str], None]) -> str | None:
    if not source.exists():
        say(f"  no dump at {source}")
        return None
    declared = declared_as(romimage.dump.read(source), manifest)
    if declared is None:
        say(f"  {source} is not a dump {identify.MANIFEST_PATH.name} declares")
        say(f"  {toolchain.launched('tools/identify.py')} says what it is")
        return None
    return output_name(declared)


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    assemble: Any = assemble,
    left: Any = unfinished,
    staged: Path | str | None = None,
    manifest: Any = None,
) -> int:
    if len(argv) < 2:
        say("usage: cartridge.py <source-rom> [<destination>]")
        return 2

    source = Path(argv[1])
    destination = (Path(argv[2]) if len(argv) > 2 else DIST) / release_folder()
    name = named_or_refused(source, identify.read_manifest() if manifest is None else manifest, say)
    if name is None:
        return 2

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

    write_forms(destination, name, final, say)
    return 0


script.entry(__name__, main, sys.argv)
