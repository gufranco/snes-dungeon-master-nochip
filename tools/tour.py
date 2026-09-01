import random
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

BUTTONS = ("up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "start", "select")
DIRECTIONS = ("up", "down", "left", "right")
CLICKS = ("a", "b")

INTRO_FRAMES = 3000
INTRO_PERIOD = 40
PRESS_FRAMES = 6
STEP_PERIOD = 14

MAX_RUN = 8
CLICKS_PER_RUN = 3


def _intro(steps: list[tuple[int, tuple[str, ...]]], frame: int) -> int:
    while frame < INTRO_FRAMES:
        steps.append((frame, ("start",)))
        steps.append((frame + PRESS_FRAMES, ()))
        frame += INTRO_PERIOD
    return frame


def _press(steps: list[tuple[int, tuple[str, ...]]], frame: int, button: str) -> int:
    steps.append((frame, (button,)))
    steps.append((frame + PRESS_FRAMES, ()))
    return frame + STEP_PERIOD


def _body(steps: list[tuple[int, tuple[str, ...]]], frame: int, frames: int, rng: Any) -> int:
    while frame + STEP_PERIOD < frames:
        direction = rng.choice(DIRECTIONS)
        for _ in range(rng.randint(1, MAX_RUN)):
            if frame + STEP_PERIOD >= frames:
                return frame
            frame = _press(steps, frame, direction)
        for _ in range(rng.randint(1, CLICKS_PER_RUN)):
            if frame + STEP_PERIOD >= frames:
                return frame
            frame = _press(steps, frame, rng.choice(CLICKS))
    return frame


def _render(steps: list[tuple[int, tuple[str, ...]]], frames: int) -> str:
    """The steps as the harness reads them, with anything past the end dropped."""
    lines: list[str] = []
    for at, buttons in steps:
        if at >= frames:
            continue
        lines.append(f"{at} {' '.join(buttons)}".rstrip())
    return "\n".join(lines) + "\n"


def build(frames: int, seed: int = 0) -> str:
    rng = random.Random(seed)
    steps: list[tuple[int, tuple[str, ...]]] = []
    frame = _intro(steps, 60)
    _body(steps, frame, frames, rng)
    return _render(steps, frames)


STEADY_PERIOD = 48

STEADY_ROUTE = ("up", "up", "up", "left", "up", "up", "up", "right")
"""A route rather than a walk, so the view redraws on every press."""


def steady(frames: int, period: int = STEADY_PERIOD) -> str:
    """One route walked at one pace, for comparing two cartridges frame by frame.

    A random walk is the right input for recording what the cartridge asks the
    chip, because it reaches many states. It is the wrong input for comparing two
    runs against each other. The harness applies a press at a fixed frame number,
    so as soon as one run drifts behind the other the same press arrives at a
    different point in that run's own logic and the two stop being the same
    playthrough. Comparing what they drew after that says nothing.

    A slow, regular route survives far more drift before that happens, and it
    still turns and steps, which is what makes the view redraw and the chip work.
    """
    steps: list[tuple[int, tuple[str, ...]]] = []
    frame = _intro(steps, 60)
    at = 0
    while frame + period < frames:
        steps.append((frame, (STEADY_ROUTE[at % len(STEADY_ROUTE)],)))
        steps.append((frame + PRESS_FRAMES, ()))
        frame += period
        at += 1
    return _render(steps, frames)


def _to_stderr(line: Any) -> None:
    print(line, file=sys.stderr)


def main(
    argv: list[str],
    say: Callable[[str], Any] | None = None,
    complain: Callable[[str], Any] | None = None,
) -> int:
    """The command line, with both streams passed in so a run can be checked."""
    say = sys.stdout.write if say is None else say
    complain = _to_stderr if complain is None else complain

    frames = 24000
    seed = 0
    out = None
    route = False

    rest = argv[1:]
    while rest:
        token = rest.pop(0)
        if token == "--frames" and rest:
            frames = int(rest.pop(0))
        elif token == "--seed" and rest:
            seed = int(rest.pop(0))
        elif token == "--out" and rest:
            out = rest.pop(0)
        elif token == "--steady":
            route = True
        else:
            complain(f"usage: tour.py [--frames N] [--seed S] [--steady] [--out PATH], got {token}")
            return 2

    text = steady(frames) if route else build(frames, seed)
    if out:
        Path(out).write_text(text)
        say(f"  wrote {out}, {len(text.splitlines())} steps over {frames:,} frames, seed {seed}")
    else:
        say(text)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    raise SystemExit(main(sys.argv))
