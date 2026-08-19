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

Result = namedtuple("Result", "path writes reads mismatches examples")


def _ok(self):
    return self.mismatches == 0


Result.ok = property(_ok)


def check(path):
    path = Path(path)
    if not path.exists():
        return None

    chip = snesdsp.Chip()
    writes = reads = mismatches = 0
    examples = []

    for record in dsptrace.records(path):
        if record.kind == dsptrace.KIND_WRITE:
            chip.write(record.byte)
            writes += 1
            continue

        produced = chip.read()
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


def main(argv):
    wanted = argv[1:] or [str(ROOT / name) for name in DEFAULT_TRACES]

    results = []
    for path in wanted:
        result = check(path)
        if result is None:
            print(f"  {Path(path).name}: no trace, skipped")
            continue
        results.append(result)
        print(explain(result))

    if not results:
        print("\n  nothing to check. Record a trace with the harness in emu/ first.")
        return 0

    reads = sum(result.reads for result in results)
    wrong = sum(result.mismatches for result in results)
    print(f"\n  {reads:,} bytes the cartridge returned, {wrong:,} the model did not reproduce")
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
