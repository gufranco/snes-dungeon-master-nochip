"""Every gate this project holds itself to, in one pass.

They were run by hand, one command each, and the list of them lived in a
document. That has two costs. One is remembering: a change lands with the tests
run and the formatter forgotten, and the runner finds it. The other is worse and
quieter, because the versions drift. Reporting coverage with a newer build than
the one that recorded it named four lines uncovered that were not, and an hour
went into looking for a gap that did not exist. Every gate here names the version
it runs, and it is the version the runner installs.

The deeper gates need the cartridge, so they need what nobody may distribute.
They are skipped, out loud, on a machine without it rather than quietly passing.
"""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import assembled  # noqa: E402

RUFF = "ruff@0.16.3"
MYPY = "mypy@1.14.1"
COVERAGE = "coverage==7.6.10"

MODULES = "*.test.py tools/*.test.py conformance/*.test.py"


class Gate(NamedTuple):
    """One check, what it runs, and whether it needs the cartridge."""

    name: str
    command: list[str]
    needs_image: bool = False


COVERED = (
    f"python3 -m coverage erase && status=0 && for one in {MODULES}; do "
    f'python3 -m coverage run -a "$one" || status=1; done && '
    f"python3 -m coverage report && exit $status"
)
"""Recording and reporting with one build, because two disagree about class bodies."""

GATES = (
    Gate("lint", ["uvx", RUFF, "check", "."]),
    Gate("format", ["uvx", RUFF, "format", "--check", "."]),
    Gate("types", ["uvx", MYPY, "."]),
    Gate("tests", ["uvx", "--from", COVERAGE, "bash", "-c", COVERED]),
    Gate("json and yaml", ["pnpm", "run", "format:check"]),
    Gate("workflows", ["actionlint"]),
    Gate("shell", ["shellcheck", "--severity=style", "--shell=bash", "scripts/set-version.sh"]),
    Gate("cost", ["python3", "tools/cost.py"], needs_image=True),
    Gate("split feed", ["python3", "splitfeed.retail.test.py"], needs_image=True),
    Gate("scale step", ["python3", "scalestep.retail.test.py"], needs_image=True),
    Gate("similarity", ["python3", "similarity.retail.test.py"], needs_image=True),
)


def _shell_out(args: list[str]) -> Any:
    return subprocess.run(args, capture_output=True, text=True, cwd=ROOT, check=False)


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    execute: Any = _shell_out,
    ready: Any = None,
) -> int:
    """Every gate, run in order, with the one that failed named."""
    ready = assembled.ready if ready is None else ready

    quick = False
    for token in argv[1:]:
        if token == "--quick":
            quick = True
        else:
            say("usage: check.py [--quick]")
            return 2

    have_image = False
    if not quick:
        have_image = ready(say=lambda _line: None) == 0
        if not have_image:
            say("  the cartridge is not here, so the gates that need it are skipped")

    failed: list[str] = []
    for gate in GATES:
        if gate.needs_image and not have_image:
            continue
        finished = execute(gate.command)
        if finished.returncode:
            failed.append(gate.name)
            say(f"  {gate.name:<14} no")
            for line in (finished.stdout or finished.stderr or "").strip().splitlines()[-6:]:
                say(f"      {line}")
        else:
            say(f"  {gate.name:<14} ok")

    if failed:
        say(f"  {len(failed)} of {len(GATES)} gates did not pass: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
