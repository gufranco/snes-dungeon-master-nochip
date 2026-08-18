import random
import sys
from pathlib import Path

BUTTONS = ("up", "down", "left", "right", "a", "b", "x", "y", "l", "r", "start", "select")
DIRECTIONS = ("up", "down", "left", "right")
CLICKS = ("a", "b")

INTRO_FRAMES = 3000
INTRO_PERIOD = 40
PRESS_FRAMES = 6
STEP_PERIOD = 14

MAX_RUN = 8
CLICKS_PER_RUN = 3


def _intro(steps, frame):
    while frame < INTRO_FRAMES:
        steps.append((frame, ("start",)))
        steps.append((frame + PRESS_FRAMES, ()))
        frame += INTRO_PERIOD
    return frame


def _press(steps, frame, button):
    steps.append((frame, (button,)))
    steps.append((frame + PRESS_FRAMES, ()))
    return frame + STEP_PERIOD


def _body(steps, frame, frames, rng):
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


def build(frames, seed=0):
    rng = random.Random(seed)
    steps = []
    frame = _intro(steps, 60)
    _body(steps, frame, frames, rng)

    lines = []
    for at, buttons in steps:
        if at >= frames:
            continue
        lines.append(f"{at} {' '.join(buttons)}".rstrip())
    return "\n".join(lines) + "\n"


def main(argv):
    frames = 24000
    seed = 0
    out = None

    rest = argv[1:]
    while rest:
        token = rest.pop(0)
        if token == "--frames" and rest:
            frames = int(rest.pop(0))
        elif token == "--seed" and rest:
            seed = int(rest.pop(0))
        elif token == "--out" and rest:
            out = rest.pop(0)
        else:
            print(
                f"usage: tour.py [--frames N] [--seed S] [--out PATH], got {token}", file=sys.stderr
            )
            return 2

    text = build(frames, seed)
    if out:
        Path(out).write_text(text)
        print(f"  wrote {out}, {len(text.splitlines())} steps over {frames:,} frames, seed {seed}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
