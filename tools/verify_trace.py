import importlib.util
import sys
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACES = ("build/trace-s1.bin", "build/trace-s2.bin", "build/trace-s3.bin")
EXAMPLE_LIMIT = 5


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
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

Result = namedtuple("Result", "path writes reads mismatches examples")


def chip():
    """One DSP-2, running the microcode of the part rather than a description of it.

    A trace is what the cartridge's own chip answered, so the only thing worth
    replaying it against is that chip's program. Nothing here carries it: a copy
    somebody already owns goes in this project's firmware directory.
    """
    return snesdsp.Dsp(PART)


def why_not():
    """Why a check cannot run here, or nothing when it can."""
    return snesdsp.why_not()


def _ok(self):
    return self.mismatches == 0


Result.ok = property(_ok)


def check(path, build=chip):
    path = Path(path)
    if not path.exists():
        return None

    part = build()
    writes = reads = mismatches = 0
    examples = []

    for record in dsptrace.records(path):
        if record.kind == dsptrace.KIND_WRITE:
            part.write(record.byte)
            writes += 1
            continue

        produced = part.read()
        reads += 1
        if produced != record.byte:
            mismatches += 1
            if len(examples) < EXAMPLE_LIMIT:
                examples.append((record.frame, record.pc, record.byte, produced))

    return Result(path=path, writes=writes, reads=reads, mismatches=mismatches, examples=examples)


def explain(result):
    lines = [
        f"  {result.path.name}: {result.writes:,} written, {result.reads:,} read, "
        f"{result.mismatches:,} wrong"
    ]
    for frame, pc, wanted, produced in result.examples:
        lines.append(
            f"      frame {frame} pc ${pc:06X} cartridge {wanted:#04x} model {produced:#04x}"
        )
    return "\n".join(lines)


def main(argv, build=chip, refuses=why_not, say=print):
    reason = refuses()
    if reason:
        say(f"  nothing to check: {reason}")
        return 2

    wanted = argv[1:] or [str(ROOT / name) for name in DEFAULT_TRACES]

    results = []
    for path in wanted:
        result = check(path, build)
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
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
