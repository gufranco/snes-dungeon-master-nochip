import importlib
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT))

import environment  # noqa: E402
import hardware  # noqa: E402
from version import VERSION  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))

identify = importlib.import_module("identify")

OLDEST_PYTHON = (3, 12)

PROJECT = "snes-dungeon-master-nochip"

ORIGIN = "https://github.com/gufranco/snes-dungeon-master-nochip.git"

NEXT_WHEN_CLEAN = "python3 cartridge.py external/roms/dungeon-master-usa.sfc"

NEXT_WHEN_NOT = "fix the first line marked ! above, then run python3 doctor.py again"

DOCKER_ANSWER_SECONDS = 30

PART = "dsp2"

TRACES = ("build/trace-s1.bin", "build/trace-s2.bin", "build/trace-s3.bin")


class Finding:
    def __init__(self, name: Any, ok: Any, detail: Any, advice: Any = None) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail
        self.advice = advice

    @property
    def line(self) -> str:
        return f"  {'ok  ' if self.ok else '   !'}  {self.name}: {self.detail}"

    @property
    def report(self) -> str:
        if self.ok or not self.advice:
            return self.line
        return f"{self.line}\n         {self.advice}"

    @override
    def __repr__(self) -> str:
        return f"<Finding {self.name} {'ok' if self.ok else 'not ok'}>"


def _python() -> Any:
    return Finding(
        "python",
        sys.version_info[:2] >= OLDEST_PYTHON,
        f"{platform.python_version()} on {platform.system()} {platform.machine()}",
        f"this project needs {OLDEST_PYTHON[0]}.{OLDEST_PYTHON[1]} or newer",
    )


def _project() -> Any:
    return Finding(PROJECT, True, f"version {VERSION}")


def is_git_checkout(root: Path = ROOT) -> bool:
    return any((folder / ".git").exists() for folder in (root, *root.parents))


def _checkout(cloned: Callable[[], bool] = is_git_checkout) -> Any:
    if cloned():
        return Finding("checkout", True, "a git clone, so the submodules can be fetched")
    return Finding(
        "checkout",
        False,
        "no git metadata, so this came from a downloaded archive",
        "a downloaded ZIP never carries the submodules and nothing can add them"
        " afterwards; delete this folder and clone instead:"
        f" git clone --recurse-submodules {ORIGIN}",
    )


def _docker_answers(run: Callable[..., Any] = subprocess.run) -> tuple[bool, str]:
    try:
        done = run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=DOCKER_ANSWER_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as trouble:
        return False, f"{type(trouble).__name__}: {trouble}"
    said = (done.stdout or done.stderr or "no answer").strip().splitlines()
    return done.returncode == 0, said[0] if said else "no answer"


def _docker_engine(
    look: Callable[[str], str | None] = shutil.which,
    ask: Callable[[], tuple[bool, str]] = _docker_answers,
) -> Any:
    if not look("docker"):
        return Finding(
            "docker engine",
            False,
            "docker is not installed",
            "install Docker Desktop on Windows or macOS, or Docker Engine on Linux,"
            " then open a new terminal so the docker command is found",
        )
    running, said = ask()
    if running:
        return Finding("docker engine", True, f"running, server {said}")
    return Finding(
        "docker engine",
        False,
        f"installed but not answering: {said}",
        "start Docker Desktop and wait until it says the engine is running, or on"
        " Linux run sudo systemctl start docker; the build assembles in a container",
    )


def _default_import(package: str) -> Any:
    hardware.install()
    return importlib.import_module(package)


def _model(package: str, where: Path | str, load: Callable[[str], Any]) -> Any:
    if not Path(where).is_dir() or not any(Path(where).iterdir()):
        return Finding(
            package,
            False,
            f"{Path(where).name} is not checked out",
            "the models live in their own repositories and are pinned here as"
            " submodules; run git submodule update --init --recursive",
        )
    try:
        found = load(package)
    except Exception as trouble:
        return Finding(
            package,
            False,
            f"{type(trouble).__name__}: {trouble}",
            "the model is here and will not import, which is the line above"
            " rather than a missing checkout",
        )
    return Finding(package, True, f"version {getattr(found, 'VERSION', 'not stated')}")


def _default_why_not() -> Any:
    return _default_import("snesdsp").why_not()


def _default_available() -> Any:
    return sorted(_default_import("snesdsp").available())


def _microcode(
    why_not: Callable[[], Any] = _default_why_not,
    available: Callable[[], Any] = _default_available,
) -> Any:
    try:
        reason = why_not()
        held = list(available())
    except Exception as trouble:
        return Finding(
            "microcode",
            False,
            f"{type(trouble).__name__}: {trouble}",
            "asking the part what it can run failed, which is itself the finding",
        )
    if reason:
        return Finding(
            "microcode",
            False,
            reason,
            f"put a copy you already own in {PROJECT}/firmware, or name another"
            " directory with UPD7725_FIRMWARE_DIR. Nothing here downloads it",
        )
    return Finding("microcode", True, f"can run {', '.join(held) or 'nothing'}")


def _default_cartridges() -> Any:
    manifest = identify.read_manifest()
    return [identify.diagnose(one, manifest) for one in manifest["artifacts"]]


def _cartridges(diagnose: Callable[[], Any] = _default_cartridges) -> list[Any]:
    try:
        found = list(diagnose())
    except Exception as trouble:
        return [
            Finding(
                "cartridge",
                False,
                f"{type(trouble).__name__}: {trouble}",
                "the manifest could not be read, so nothing here says which dump"
                " this project wants",
            )
        ]
    lines: list[Any] = []
    for one in found:
        digest = f", sha256 {one.identity.sha256}" if one.identity else ""
        lines.append(
            Finding(
                f"cartridge {one.filename}",
                one.state in (identify.STATE_OK, identify.STATE_UNDECLARED),
                f"{one.state}{': ' + one.detail if one.detail else ''}{digest}",
                "the digests this project accepts are published in"
                " artifacts.manifest.json; nothing here says where to obtain a dump",
            )
        )
    return lines


def _traces(root: Path | str = ROOT) -> Any:
    found = [name for name in TRACES if (Path(root) / name).exists()]
    return Finding(
        "recorded traffic",
        True,
        f"{len(found)} of {len(TRACES)} traces here"
        if found
        else "none recorded, so the checks that replay one will skip",
    )


def _default_beneath() -> Any:
    return _ask_each(sorted(hardware.PACKAGES), hardware.root_of, importlib.import_module)


def _ask_each(packages: Any, locate: Callable[[str], Any], load: Callable[[str], Any]) -> list[Any]:
    found: list[Any] = []
    for package in packages:
        where = Path(locate(package))
        if not where.is_dir():
            continue
        if str(where) not in sys.path:
            sys.path.insert(0, str(where))
        try:
            underneath = load(f"{package}.doctor")
        except ModuleNotFoundError:
            continue
        found.extend((where.name, one) for one in underneath.examine())
    return found


def _default_unused(load: Callable[[str], Any] = _default_import) -> Any:
    try:
        return sorted(set(load("snesdsp").MODELS) - {PART})
    except Exception:
        return []


def _beneath(beneath: Any, unused: Callable[..., Any] = _default_unused) -> list[Any]:
    try:
        found = list(beneath())
    except Exception as trouble:
        return [
            Finding(
                "the models underneath",
                False,
                f"{type(trouble).__name__}: {trouble}",
                "one of the models could not be examined; it is either not checked"
                " out or older than this project expects, and both are fixed by"
                " running git submodule update --init --recursive",
            )
        ]
    elsewhere = set(unused())
    lines: list[Any] = []
    for where, one in found:
        spare = one.name in elsewhere and not one.ok
        lines.append(
            Finding(
                f"{where} / {one.name}",
                one.ok or spare,
                f"{one.detail}, and this cartridge does not carry it" if spare else one.detail,
                None if spare else one.advice,
            )
        )
    return lines


def examine(
    load: Callable[[str], Any] = _default_import,
    beneath: Callable[[], Any] = _default_beneath,
) -> list[Any]:
    found = [_python(), _project(), _checkout()]
    found.extend(
        _model(package, hardware.root_of(package), load) for package in sorted(hardware.PACKAGES)
    )
    found.append(_microcode())
    found.extend(_cartridges())
    found.append(_traces())
    found.append(_docker_engine())
    found.extend(_beneath(beneath))
    return found


def report(found: Any) -> list[str]:
    unwell = [one for one in found if not one.ok]
    lines = [f"{PROJECT} {VERSION} on {platform.python_version()}, {platform.system()}", ""]
    lines.append("  the machine")
    lines.extend(environment.lines(ROOT))
    lines.append("")
    lines.append("  this package")
    lines.extend(one.report for one in found)
    lines.append("")
    if unwell:
        lines.append(f"  {len(unwell)} of {len(found)} checks did not pass")
        lines.append(f"  next: {NEXT_WHEN_NOT}")
    else:
        lines.append(f"  {len(found)} checks, nothing to report")
        lines.append(f"  next: {NEXT_WHEN_CLEAN}")
    return lines


def main(
    argv: tuple[str, ...] | list[str] = (),
    examine: Callable[..., Any] = examine,
    say: Callable[[str], None] = print,
) -> int:
    found = examine()
    for line in report(found):
        say(line)
    return 1 if any(not one.ok for one in found) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
