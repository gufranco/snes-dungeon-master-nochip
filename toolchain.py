from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent

ASSEMBLER = "asar"

EMULATOR = "dmemu"

PROGRAMS = (ASSEMBLER, EMULATOR)

LAUNCHER = "./run.sh"

WINDOWS_LAUNCHER = ".\\run.cmd"


def command(
    program: str,
    settings: Sequence[str] = (),
    args: Sequence[str] = (),
    where: Path = ROOT,
) -> list[str]:
    return ["env", f"--chdir={where}", *settings, program, *args]


def launched(script: str) -> str:
    return f"{LAUNCHER} {script}, or on Windows {WINDOWS_LAUNCHER} {script}"


def missing_message(program: str) -> str:
    return (
        f"{program} is not in this environment. Every tool this project runs lives in its "
        f"container image, so start the command through the launcher: {launched('<script>')}"
    )
