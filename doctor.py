"""Look at this machine and say what is actually here, so a report can be believed.

This project is the end of a chain. It measures a converted cartridge against a
retail one, using models that live in other repositories, one of which runs a
part's own microcode, which belongs to whoever made the part. Any link can be
missing on a given machine, and from outside they all look the same: it does not
work.

So this looks, and prints what it found in a form that can be pasted into an
issue as it stands.

It asks the models it is built on for their own reports too, and files what comes
back under their names. That is recursive by construction: whatever they examine,
including anything they are built on in turn, arrives with it. A project can be
entirely well while the thing underneath it is stale, and a report that looked
only here would come back clean in exactly that case.

Two rules shape the rest. Nothing is hidden: a check that fails says what it saw,
and a check that itself throws is reported as what it threw, named by type.
Nothing is inferred: every line is something looked at on this machine just now.

No byte of anybody's cartridge is printed. The digest of a dump identifies it
without carrying it, which is the whole reason digests are published.
"""

import importlib
import platform
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT))

import hardware  # noqa: E402
from version import VERSION  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))

identify = importlib.import_module("identify")

OLDEST_PYTHON = (3, 12)

PROJECT = "dungeon-master-nochip"

PART = "dsp2"
"""The coprocessor this cartridge carries, and the microcode a check runs against."""

TRACES = ("build/trace-s1.bin", "build/trace-s2.bin", "build/trace-s3.bin")


class Finding:
    """One thing that was looked at, and what was there."""

    def __init__(self, name: Any, ok: Any, detail: Any, advice: Any = None) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail
        self.advice = advice

    @property
    def line(self) -> str:
        """The one-line form, which is what a reader scans."""
        return f"  {'ok  ' if self.ok else '   !'}  {self.name}: {self.detail}"

    @property
    def report(self) -> str:
        """The same, with what to do about it when there is something to do."""
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


def _default_import(package: str) -> Any:
    hardware.install()
    return importlib.import_module(package)


def _model(package: str, where: Path | str, load: Callable[[str], Any]) -> Any:
    """Whether that model is checked out and imports, and which version it is."""
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
    """Whether the coprocessor can actually run here.

    The model runs the part's own program, which nothing in any of these
    repositories carries. Without a copy the checks that drive the part cannot
    run at all, and saying so plainly is better than a traceback from the first
    thing that tries.
    """
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
    """Every dump this project reads, and whether the one here is the one it wants.

    A region with no digests published yet is reported and is not a failure. It
    says something true about the project rather than about the machine running
    it, and a report that came back unwell on every machine would stop being read.
    """
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
    """The recorded cartridge traffic, which is what the routines are checked against."""
    found = [name for name in TRACES if (Path(root) / name).exists()]
    return Finding(
        "recorded traffic",
        True,
        f"{len(found)} of {len(TRACES)} traces here"
        if found
        else "none recorded, so the checks that replay one will skip",
    )


def _default_beneath() -> Any:
    """Every model that carries a doctor, asked for its own report.

    A model with no doctor is passed over rather than reported: not every one of
    them has grown one yet, and a line saying so on every run would be noise. A
    model whose doctor is here and will not run is a different thing entirely and
    is left to raise, because that is a real fault on this machine.
    """
    return _ask_each(sorted(hardware.PACKAGES), hardware.root_of, importlib.import_module)


def _ask_each(packages: Any, locate: Callable[[str], Any], load: Callable[[str], Any]) -> list[Any]:
    """Each named model asked for its report, skipping the ones that have none."""
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
    """The parts the coprocessor model covers that this cartridge does not carry.

    A model that will not import at all is reported by its own check above, so
    here it means only that nothing can be said about which parts are spare.
    Saying nothing is right: every finding then stands as the model wrote it.
    """
    try:
        return sorted(set(load("snesdsp").MODELS) - {PART})
    except Exception:
        return []


def _beneath(beneath: Any, unused: Callable[..., Any] = _default_unused) -> list[Any]:
    """Everything the models found, each filed under the name of its repository.

    One adjustment is made on the way through, and it is worth saying exactly
    what it is. The coprocessor model covers six parts and reports a missing
    image for each. This cartridge carries one of them. A missing image for the
    other five is a true statement about this machine and not a fault of it, so
    the line is kept, in full, and stops being counted as a failure. Nothing is
    removed: a report that hid those lines would be hiding the one thing somebody
    checking a digest needs to see.
    """
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
    """Everything worth looking at on this machine, in the order a reader wants it."""
    found = [_python(), _project()]
    found.extend(
        _model(package, hardware.root_of(package), load) for package in sorted(hardware.PACKAGES)
    )
    found.append(_microcode())
    found.extend(_cartridges())
    found.append(_traces())
    found.extend(_beneath(beneath))
    return found


def report(found: Any) -> list[str]:
    """The lines a person pastes into an issue."""
    unwell = [one for one in found if not one.ok]
    lines = [f"{PROJECT} {VERSION} on {platform.python_version()}, {platform.system()}", ""]
    lines.extend(one.report for one in found)
    lines.append("")
    if unwell:
        lines.append(f"  {len(unwell)} of {len(found)} checks did not pass")
    else:
        lines.append(f"  {len(found)} checks, nothing to report")
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
