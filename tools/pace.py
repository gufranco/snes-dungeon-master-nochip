import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import toolchain  # noqa: E402


def _load_beside(name: str) -> Any:
    where = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tour = _load_beside("tour")


SCRIPT = "pace.script"

HASHES_RETAIL = "pace-retail.txt"
HASHES_CONVERTED = "pace-converted.txt"

DEFAULT_FRAMES = 4000


def digests(path: Path) -> list[str]:
    found: list[str] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3:
            found.append(parts[1])
    return found


WINDOW = 120


def lags(retail: list[str], converted: list[str], window: int = WINDOW) -> list[int | None]:
    found: list[int | None] = []
    at = 0
    for index, digest in enumerate(retail):
        ahead = next(
            (j for j in range(at, min(len(converted), at + window)) if converted[j] == digest),
            None,
        )
        if ahead is None:
            found.append(None)
            continue
        found.append(max(0, ahead - index))
        at = ahead + 1
    return found


def curve(found: list[int | None], steps: int = 8) -> list[tuple[int, int]]:
    matched = [(index, lag) for index, lag in enumerate(found) if lag is not None]
    if not matched:
        return []
    width = max(1, len(matched) // steps)
    points: list[tuple[int, int]] = []
    for start in range(0, len(matched), width):
        window = matched[start : start + width]
        lags_here = sorted(lag for _index, lag in window)
        points.append((window[0][0], lags_here[len(lags_here) // 2]))
    return points


def summary(found: list[int | None], frames: int) -> str:
    matched = [one for one in found if one is not None]
    if not matched:
        return f"  followed nothing of {frames:,} frames, so the two runs never matched"

    unmatched = len(found) - len(matched)
    late = [one for one in matched if one]
    reach = f"followed {len(matched):,} of {frames:,} frames, {unmatched:,} never drawn the same"
    if not late:
        return f"  {reach}, and the conversion never fell behind"
    worst = max(late)
    typical = sorted(late)[len(late) // 2]
    return f"  {reach}, {len(late):,} behind, worst {worst} frames, median {typical}"


def run_command(work: Path, cartridge: str, hashes: str, frames: int) -> list[str]:
    return toolchain.command(
        toolchain.EMULATOR,
        [f"DMSCRIPT={SCRIPT}", f"DMHASH={hashes}"],
        [cartridge, str(frames)],
        work.resolve(),
    )


def _shell_out(args: list[str]) -> Any:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    execute: Any = _shell_out,
) -> int:
    if len(argv) < 3:
        say("usage: pace.py <retail-rom> <converted-rom> [frames]")
        return 2

    retail, converted = Path(argv[1]), Path(argv[2])
    frames = DEFAULT_FRAMES if len(argv) < 4 else int(argv[3])

    missing = [str(one) for one in (retail, converted) if not one.exists()]
    if missing:
        say(f"  cannot find {', '.join(missing)}")
        return 2

    work = converted.parent
    (work / SCRIPT).write_text(tour.steady(frames))

    if retail.resolve().parent != work.resolve():
        shutil.copyfile(retail, work / retail.name)
        retail = work / retail.name

    for cartridge, hashes in ((retail, HASHES_RETAIL), (converted, HASHES_CONVERTED)):
        finished = execute(run_command(work, cartridge.name, hashes, frames))
        if finished.returncode:
            say(f"  {cartridge.name} did not run: {finished.stderr or finished.stdout}")
            return 1

    found = lags(digests(work / HASHES_RETAIL), digests(work / HASHES_CONVERTED))
    say(summary(found, frames))
    for at, lag in curve(found):
        say(f"    from frame {at:>6,}  {lag:>4} frames behind")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    raise SystemExit(main(sys.argv))
