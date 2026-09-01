import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASM_DIR = ROOT / "asm"
IMAGE = "snes-dungeon-master-nochip/asar:1.81"


def build_image_command() -> list[str]:
    return [
        "docker",
        "build",
        "--tag",
        IMAGE,
        str(ASM_DIR),
    ]


def patch_command(work_dir: Path | str, patch_name: str, rom_name: str) -> list[str]:
    """What assembling shells out to, asking for the label table as well.

    The table is emitted on a pass of its own and only when asked for, so a
    build without this flag leaves whatever the last one wrote. Anything that
    then enters a routine by name enters it where it used to be.
    """
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--volume",
        f"{work_dir}:/work",
        IMAGE,
        "--symbols=wla",
        f"--symbols-path={Path(rom_name).with_suffix('.sym').name}",
        patch_name,
        rom_name,
    ]


def staged_path(patch: Path | str, output_name: str) -> Path:
    """Where the assembler's output lands, which is beside the source it assembles.

    The container mounts that directory and nothing else, so the image is
    written there rather than wherever the caller wants it afterwards.
    """
    return Path(patch).resolve().parent / output_name


def stage_rom(source: Path | str, work_dir: Path | str, output_name: str) -> Path:
    target = Path(work_dir) / output_name
    if target.resolve() == Path(source).resolve():
        raise ValueError("refusing to patch the source ROM in place")
    shutil.copy2(source, target)
    return target


def run(
    args: list[str],
    execute: Callable[[list[str]], int] | None = None,
    say: Callable[[str], None] = print,
) -> int:
    """One command, printed before it runs so a failing build says what it ran."""
    say("  $ " + " ".join(args))
    if execute is None:
        return subprocess.run(args, text=True, check=False).returncode
    return execute(args)


def wants_image_only(argv: list[str]) -> bool:
    return len(argv) == 2 and argv[1] == "--image"


def main(
    argv: list[str] | None = None,
    execute: Callable[[list[str]], int] | None = None,
    say: Callable[[str], None] = print,
    complain: Callable[[str], None] | None = None,
) -> int:
    """The command line, with the shelling out passed in so it can be checked."""
    argv = sys.argv if argv is None else argv
    complain = say if complain is None else complain

    if wants_image_only(argv):
        return run(build_image_command(), execute, say)

    if len(argv) < 4:
        complain("usage: build.py <patch.asm> <source-rom> <output-rom>")
        complain("       build.py --image        (build the toolchain image only)")
        return 2

    patch, source, output = argv[1], Path(argv[2]), argv[3]
    work = Path(patch).resolve().parent

    if run(build_image_command(), execute, say) != 0:
        complain("toolchain image failed to build")
        return 1

    staged = stage_rom(source, work, output)
    say(f"  staged {source} -> {staged}")

    code = run(patch_command(work, Path(patch).name, output), execute, say)
    if code == 0:
        say(f"[done] {staged} ({staged.stat().st_size:,} bytes)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
