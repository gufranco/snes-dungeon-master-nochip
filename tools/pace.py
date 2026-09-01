"""Whether the conversion keeps up, which the cycle count does not answer.

The cost report says the routines add most of a frame of processor time to each
frame. That is a sum over the commands the cartridge issues, and it is not the
question a player has. A game that spends its spare time waiting for vblank can
absorb a great deal of extra work and still draw sixty times a second; one that
was already close to the edge cannot absorb any.

So this compares the two cartridges rather than counting. Both are driven with
the same input, frame by frame, and the emulator digests each finished frame.
Two runs that stay in step produce the same digest at the same index. When the
converted one falls behind, the picture the retail run showed at frame n turns
up later, and how much later is the answer.

Its limits are worth stating. The emulator answers a chip command in no time at
all, so the retail run here is faster than the cartridge ever was, which makes
this an upper bound on the gap rather than a measurement of it. And a digest
covers the whole frame, so anything that changes every frame regardless of the
dungeon view, a blinking cursor, an animated sprite, would leave every frame
looking different and no lag measurable at all. On these runs that does not
happen; if it starts to, this reports that it could follow almost nothing rather
than reporting a small lag.
"""

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _load_beside(name: str) -> Any:
    """A module that sits next to this one, loaded the way the tools load each other."""
    where = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tour = _load_beside("tour")

EMULATOR = "dungeon-master-nochip/emu:dev"

SCRIPT = "pace.script"
"""The input both cartridges are driven with, which this writes before each run.

It used to be a file the caller was expected to have put there, which nothing in
this repository produced. A fresh clone therefore ran both cartridges with no
input at all, left them on the title screen, and compared two runs that agreed
perfectly because neither did anything.

A random walk would be the wrong input even when present. It presses often and
in runs, so the two cartridges stop being the same playthrough as soon as one
drifts, and driven by one this follows 3,403 frames of 9,000 and then reports
nothing it can use. The steady route survives 29,936 of 30,000, and it is not a
lighter load: it provokes more chip work over the same span than the walk does.
"""

HASHES_RETAIL = "pace-retail.txt"
HASHES_CONVERTED = "pace-converted.txt"

DEFAULT_FRAMES = 4000


def digests(path: Path) -> list[str]:
    """One digest a frame, in the order the run produced them."""
    found: list[str] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3:
            found.append(parts[1])
    return found


WINDOW = 120
"""How far ahead a picture is looked for before the frame is called unmatched.

Two seconds. A frame that has not appeared by then is not late, it is different,
and the two are worth telling apart: an unbounded search spends the rest of the
stream looking for one picture that never comes and reports every frame after it
as unfollowable. That is what the first version did, and on a run where 3,289 of
4,000 frames were identical it reported that it could follow 25.
"""


def lags(retail: list[str], converted: list[str], window: int = WINDOW) -> list[int | None]:
    """For each frame the retail run drew, how many frames later the other drew it.

    The search only ever moves forward, so a picture that comes back later in the
    run cannot be matched against an earlier frame and report a lag of zero that
    was never real. A frame it cannot find inside the window is None, and the
    cursor stays where it was rather than being spent looking.
    """
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
    """The lag at points across the run, so its shape is visible rather than its middle.

    A median hides the difference that matters. A conversion that is steadily
    slower falls further behind every frame; one that stalls once on a heavy
    scene and then keeps pace holds the same lag for the rest of the run. Both
    produce the same median and only one of them is a problem.
    """
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
    """What the lags add up to, in one line."""
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
    """What one run shells out to."""
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "-e",
        f"DMSCRIPT={SCRIPT}",
        "-e",
        f"DMHASH={hashes}",
        "-v",
        f"{work.resolve()}:/work",
        EMULATOR,
        cartridge,
        str(frames),
    ]


def _shell_out(args: list[str]) -> Any:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    execute: Any = _shell_out,
) -> int:
    """Both cartridges driven with the same input, and how far apart they end up."""
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
    raise SystemExit(main(sys.argv))
