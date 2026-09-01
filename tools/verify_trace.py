import importlib.util
import sys
from collections import namedtuple
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACES = ("build/trace-s1.bin", "build/trace-s2.bin", "build/trace-s3.bin")
EXAMPLE_LIMIT = 5


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dsptrace = _load("dsptrace")

sys.path.insert(0, str(ROOT))
import hardware  # noqa: E402

hardware.install()

import snesdsp  # noqa: E402

PART = "dsp2"
"""The part this cartridge carries, and the microcode a check runs against."""

CAVEAT = (
    "  this comparison is not sound yet: the model answers a byte for the sync"
    " command and the cartridge's chip answers none, so the read streams run out"
    " of step. See OPEN-QUESTIONS.md. The routines are held by tools/replay.py."
)
"""Said with every result, because a number nobody can trust reads like one they can.

What this reports is real and it is not evidence about the routines. It replays a
raw byte stream against the part's microcode, and the two disagree about whether
sync produces output, which puts every later read one byte out. The arithmetic
agrees wherever it has been checked one transaction at a time.
"""

Result = namedtuple("Result", "path writes reads mismatches examples")


def chip(build: Any = None) -> Any:
    """One DSP-2, running the microcode of the part rather than a description of it.

    A trace is what the cartridge's own chip answered, so the only thing worth
    replaying it against is that chip's program. Nothing here carries it: a copy
    somebody already owns goes in this project's firmware directory.
    """
    return (build or snesdsp.Chip)(PART)


def why_not() -> Any:
    """Why a check cannot run here, or nothing when it can."""
    return snesdsp.why_not()


def _ok(self: Any) -> bool:
    found: bool = self.mismatches == 0
    return found


Result.ok = property(_ok)  # type: ignore[attr-defined]


PROGRESS = 2_000_000
"""Records between one word about where the run is and the next.

A trace holds sixty million of them and the part answers each one by running its
own microcode, so a single trace takes hours. Reporting only at the end means a
run that is killed for taking too long produces nothing at all, which is what
happened: three hours of processor time, no output, nothing learned. Roughly two
million records is a line every few minutes.
"""


def check(
    path: Any,
    build: Any = chip,
    say: Callable[[str], None] | None = None,
    every: int = PROGRESS,
    limit: int = 0,
) -> Any:
    """A whole trace, or as much of it as asked for, replayed against the part."""
    path = Path(path)
    if not path.exists():
        return None

    part = build()
    writes = reads = mismatches = 0
    examples: list[Any] = []

    for record in dsptrace.records(path):
        if record.kind == dsptrace.KIND_WRITE:
            part.write(record.byte)
            writes += 1
        else:
            produced = part.read()
            reads += 1
            if produced != record.byte:
                mismatches += 1
                if len(examples) < EXAMPLE_LIMIT:
                    examples.append((record.frame, record.pc, record.byte, produced))

        seen = writes + reads
        if say is not None and seen % every == 0:
            say(f"  {path.name}: {seen:,} records, {mismatches:,} wrong so far")
        if limit and seen >= limit:
            break

    return Result(path=path, writes=writes, reads=reads, mismatches=mismatches, examples=examples)


def explain(result: Any) -> str:
    lines = [
        f"  {result.path.name}: {result.writes:,} written, {result.reads:,} read, "
        f"{result.mismatches:,} wrong"
    ]
    for frame, pc, wanted, produced in result.examples:
        lines.append(
            f"      frame {frame} pc ${pc:06X} cartridge {wanted:#04x} model {produced:#04x}"
        )
    return "\n".join(lines)


def main(
    argv: list[str],
    build: Any = chip,
    refuses: Any = why_not,
    say: Callable[[str], None] = print,
) -> int:
    reason = refuses()
    if reason:
        say(f"  nothing to check: {reason}")
        return 2

    rest = argv[1:]
    limit = 0
    if rest and rest[0].isdigit():
        limit = int(rest.pop(0))
    wanted = rest or [str(ROOT / name) for name in DEFAULT_TRACES]

    results: list[Any] = []
    for path in wanted:
        result = check(path, build, say=say, limit=limit)
        if result is None:
            say(f"  {Path(path).name}: no trace, skipped")
            continue
        results.append(result)
        say(explain(result))

    if not results:
        say("\n  nothing to check. Record a trace with the harness in emu/ first.")
        return 0

    reads = sum(result.reads for result in results)
    wrong = sum(result.mismatches for result in results)
    say(f"\n  {reads:,} bytes the cartridge returned, {wrong:,} the part did not reproduce")
    say(CAVEAT)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    raise SystemExit(main(sys.argv))
