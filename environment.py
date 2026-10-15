import contextlib
import locale
import platform
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple


class Observation(NamedTuple):
    name: str
    ok: bool
    detail: str
    advice: str | None


INTERPRETERS = ("python3", "python", "py")

UTF8_NAMES = ("utf-8", "utf8", "utf_8", "cp65001")

WINDOWS_PATH_LIMIT = 260

CHECKOUT_ROOM = 60

ROOM_WANTED = 2 * 1024**3

GENERATED = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".pytest_cache",
    }
)

TEXT_SUFFIXES = (".md", ".py", ".yml", ".yaml", ".json", ".toml", ".txt", ".cfg")

SAMPLE = 200


def interpreter(look: Callable[[str], bool] | None = None) -> Observation:
    resolve = (lambda name: shutil.which(name) is not None) if look is None else look
    for name in INTERPRETERS:
        if resolve(name):
            spoken = "py -3" if name == "py" else name
            return Observation("interpreter", True, f"{spoken} runs this Python", None)
    return Observation(
        "interpreter",
        False,
        "none of python3, python or py resolved on PATH",
        "Install Python from python.org and tick the box that adds it to PATH.",
    )


DISCOVER = "<discover>"


def output_encoding(encoding: str | None = DISCOVER) -> Observation:
    found = sys.stdout.encoding if encoding == DISCOVER else encoding
    if found is None:
        return Observation(
            "output encoding",
            False,
            "this terminal does not say what encoding it uses",
            "Set PYTHONUTF8=1 before running, so the output is UTF-8 whatever the terminal says.",
        )
    if found.lower().replace("-", "").replace("_", "") in {
        one.replace("-", "").replace("_", "") for one in UTF8_NAMES
    }:
        return Observation("output encoding", True, found, None)
    return Observation(
        "output encoding",
        False,
        f"{found}, which cannot print everything this reports",
        "Set PYTHONUTF8=1, or run `chcp 65001` first on Windows.",
    )


def line_endings(root: Path, sample: int = SAMPLE) -> Observation:
    looked = converted = 0
    for path in sorted(root.rglob("*")):
        if looked >= sample:
            break
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part.startswith(".") or part == "node_modules" for part in path.parts):
            continue
        try:
            head = path.read_bytes()[:4096]
        except OSError:
            continue
        looked += 1
        if b"\r\n" in head:
            converted += 1
    if not looked:
        return Observation("line endings", True, "nothing here to read", None)
    if converted:
        return Observation(
            "line endings",
            False,
            f"{converted} of {looked} sampled text files use carriage returns",
            "git config core.autocrlf false, then delete the checkout and clone again. "
            "Every digest and every formatter check disagrees while this is set.",
        )
    return Observation("line endings", True, f"line feeds in {looked} sampled files", None)


def filesystem_case(root: Path, insensitive: bool | None = None) -> Observation:
    if insensitive is not None:
        return _case_verdict(insensitive)
    probe = root / ".doctor-case-probe"
    try:
        probe.write_bytes(b"")
        insensitive = (root / ".DOCTOR-CASE-PROBE").exists()
    except OSError as thrown:
        return Observation("filesystem case", True, f"could not probe: {thrown!r}", None)
    finally:
        with contextlib.suppress(OSError):
            probe.unlink()
    return _case_verdict(insensitive)


def _case_verdict(insensitive: bool) -> Observation:
    if insensitive:
        return Observation(
            "filesystem case",
            True,
            "case insensitive, so a wrongly cased import passes here and fails on Linux",
            None,
        )
    return Observation("filesystem case", True, "case sensitive", None)


def path_budget(root: Path, windows: bool | None = None, longest: int | None = None) -> Observation:
    on_windows = platform.system() == "Windows" if windows is None else windows
    if longest is not None:
        return _budget_verdict(longest, "", on_windows, generated=False)

    tracked = generated = 0
    where_generated = ""
    for one in root.rglob("*"):
        parts = one.relative_to(root).parts
        length = len(str(one.relative_to(root)))
        if any(part in GENERATED for part in parts):
            if length > generated:
                generated, where_generated = length, parts[0]
            continue
        tracked = max(tracked, length)
    if generated > tracked:
        return _budget_verdict(generated, where_generated, on_windows, generated=True)
    return _budget_verdict(tracked, "", on_windows, generated=False)


def _budget_verdict(longest: int, where: str, on_windows: bool, generated: bool) -> Observation:
    room = WINDOWS_PATH_LIMIT - longest
    named = f", deepest under {where}" if where else ""
    detail = (
        f"{longest} characters from the repository root{named}, leaving {room} for a checkout path"
    )
    if room > CHECKOUT_ROOM:
        return Observation("path length", True, detail, None)
    if generated:
        return Observation(
            "path length",
            True,
            detail + ", all of it generated rather than tracked",
            None,
        )
    if on_windows:
        return Observation(
            "path length",
            False,
            detail,
            "Windows stops at 260 characters. Enable LongPathsEnabled in the registry, "
            "or clone somewhere short such as C:\\src.",
        )
    return Observation(
        "path length",
        False,
        detail,
        "This machine does not care, but Windows stops at 260 characters, so a checkout "
        "there would need a very short path. Enable LongPathsEnabled or clone to C:\\src.",
    )


def tool(
    name: str,
    look: Callable[[str], str | None] | None = None,
    required: bool = True,
) -> Observation:
    resolve = shutil.which if look is None else look
    where = resolve(name)
    if where:
        return Observation(f"tool {name}", True, str(where), None)
    if required:
        return Observation(
            f"tool {name}",
            False,
            "not found on PATH",
            f"Install {name} and make sure the shell can see it.",
        )
    return Observation(f"tool {name}", True, "not found on PATH, and not needed to run", None)


def free_space(root: Path, measure: Callable[[Path], int] | None = None) -> Observation:
    read = (lambda path: shutil.disk_usage(path).free) if measure is None else measure
    try:
        free = read(root)
    except OSError as thrown:
        return Observation(
            "free space",
            False,
            f"could not be measured: {thrown!r}",
            "Check the drive is mounted and readable.",
        )
    gigabytes = free / 1024**3
    if free < ROOM_WANTED:
        return Observation(
            "free space",
            False,
            f"{gigabytes:.1f} GB free",
            f"Free up space: a build wants about {ROOM_WANTED / 1024**3:.0f} GB.",
        )
    return Observation("free space", True, f"{gigabytes:.1f} GB free", None)


def machine() -> Observation:
    return Observation(
        "machine",
        True,
        f"{platform.system()} {platform.release()} on {platform.machine()}, "
        f"{platform.python_implementation()} {platform.python_version()} "
        f"({'64' if sys.maxsize > 2**32 else '32'} bit)",
        None,
    )


def locale_setting(preferred: str | None = None, utf8: int | None = None) -> Observation:
    preferred = locale.getpreferredencoding(False) if preferred is None else preferred
    utf8 = getattr(sys.flags, "utf8_mode", 0) if utf8 is None else utf8
    detail = f"{preferred}, UTF-8 mode {'on' if utf8 else 'off'}"
    if utf8 or preferred.lower().replace("-", "") == "utf8":
        return Observation("default encoding", True, detail, None)
    return Observation(
        "default encoding",
        False,
        detail,
        "Set PYTHONUTF8=1. Reading a UTF-8 file without naming the encoding fails here.",
    )


def guarded(name: str, check: Callable[[Path], Observation], root: Path) -> Observation:
    try:
        return check(root)
    except Exception as thrown:
        return Observation(
            name,
            False,
            f"the check itself raised {type(thrown).__name__}: {thrown}",
            "This is a fault in the doctor rather than in your machine. Please report it.",
        )


CHECKS: tuple[tuple[str, Callable[[Path], Observation]], ...] = (
    ("machine", lambda _root: machine()),
    ("interpreter", lambda _root: interpreter()),
    ("output encoding", lambda _root: output_encoding()),
    ("default encoding", lambda _root: locale_setting()),
    ("filesystem case", filesystem_case),
    ("line endings", line_endings),
    ("path length", path_budget),
    ("free space", free_space),
    ("tool git", lambda _root: tool("git")),
)


def observations(root: Path) -> list[Observation]:
    return [guarded(name, check, root) for name, check in CHECKS]


def lines(root: Path, found: list[Observation] | None = None) -> list[str]:
    found = observations(root) if found is None else found
    out = [f"  {'ok  ' if one.ok else '   !'}  {one.name}: {one.detail}" for one in found]
    for one in found:
        if not one.ok and one.advice:
            out.append(f"         {one.name}: {one.advice}")
    return out


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    for line in lines(root):
        print(line)
    return 0 if all(one.ok for one in observations(root)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
