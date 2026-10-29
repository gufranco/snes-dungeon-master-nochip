import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASM_DIR = ROOT / "asm"
sys.path.insert(0, str(ROOT))

import toolchain  # noqa: E402


class ToolchainMissing(Exception): ...


def patch_command(work_dir: Path | str, patch_name: str, rom_name: str) -> list[str]:
    return toolchain.command(
        toolchain.ASSEMBLER,
        (),
        [
            "--symbols=wla",
            f"--symbols-path={Path(rom_name).with_suffix('.sym').name}",
            patch_name,
            rom_name,
        ],
        Path(work_dir),
    )


def staged_path(patch: Path | str, output_name: str) -> Path:
    return Path(patch).resolve().parent / output_name


def stage_rom(source: Path | str, work_dir: Path | str, output_name: str) -> Path:
    target = Path(work_dir) / output_name
    if target.resolve() == Path(source).resolve():
        raise ValueError("refusing to patch the source ROM in place")
    shutil.copy2(source, target)
    return target


def require(program: str, look: Callable[[str], str | None] = shutil.which) -> None:
    if not look(program):
        raise ToolchainMissing(toolchain.missing_message(program))


def run(
    args: list[str],
    execute: Callable[[list[str]], int] | None = None,
    say: Callable[[str], None] = print,
) -> int:
    say("  $ " + " ".join(args))
    if execute is None:
        execute = _shell_out
    try:
        return execute(args)
    except FileNotFoundError as absent:
        raise ToolchainMissing(toolchain.missing_message(args[0])) from absent


def _shell_out(args: list[str]) -> int:
    return subprocess.run(args, text=True, check=False).returncode


def main(
    argv: list[str] | None = None,
    execute: Callable[[list[str]], int] | None = None,
    say: Callable[[str], None] = print,
    complain: Callable[[str], None] | None = None,
    look: Callable[[str], str | None] = shutil.which,
) -> int:
    argv = sys.argv if argv is None else argv
    complain = say if complain is None else complain

    if len(argv) < 4:
        complain("usage: build.py <patch.asm> <source-rom> <output-rom>")
        return 2

    require(toolchain.ASSEMBLER, look)
    patch, source, output = argv[1], Path(argv[2]), argv[3]
    work = Path(patch).resolve().parent

    staged = stage_rom(source, work, output)
    say(f"  staged {source} -> {staged}")

    code = run(patch_command(work, Path(patch).name, output), execute, say)
    if code == 0:
        say(f"[done] {staged} ({staged.stat().st_size:,} bytes)")
    return code


def cli() -> int:
    try:
        return main()
    except ToolchainMissing as absent:
        print(absent, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
