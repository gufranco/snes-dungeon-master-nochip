import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import assembled  # noqa: E402

MODULES = "*.test.py tools/*.test.py conformance/*.test.py"


class Gate(NamedTuple):
    name: str
    command: list[str]
    needs_image: bool = False


COVERED = (
    f"coverage erase && status=0 && for one in {MODULES}; do "
    f'coverage run -a "$one" || status=1; done && '
    f"coverage report && exit $status"
)

GATES = (
    Gate("lint", ["ruff", "check", "."]),
    Gate("format", ["ruff", "format", "--check", "."]),
    Gate("types", ["mypy", "."]),
    Gate("tests", ["sh", "-c", COVERED]),
    Gate("json and yaml", ["prettier", "--check", "**/*.{json,yml,yaml}"]),
    Gate("workflows", ["actionlint"]),
    Gate("shell", ["shellcheck", "--severity=style", "scripts/set-version.sh", "run.sh"]),
    Gate("cost", ["python3", "tools/cost.py"], needs_image=True),
    Gate("split feed", ["python3", "splitfeed.retail.test.py"], needs_image=True),
    Gate("scale step", ["python3", "scalestep.retail.test.py"], needs_image=True),
    Gate("similarity", ["python3", "similarity.retail.test.py"], needs_image=True),
    Gate("multiply", ["python3", "tools/verify_multiply.py"], needs_image=True),
    Gate("merge", ["python3", "tools/verify_merge.py"], needs_image=True),
    Gate("tile and mirror", ["python3", "tools/verify_commands.py"], needs_image=True),
)


def _shell_out(args: list[str]) -> Any:
    return subprocess.run(args, capture_output=True, text=True, cwd=ROOT, check=False)


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    execute: Any = _shell_out,
    ready: Any = None,
) -> int:
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
