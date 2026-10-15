import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SOURCE = ROOT / "asm" / "dsp2-state.asm"

PAGE = 0x100

WIDTHS = {"16 bit": 2, "24 bit": 3, "32 bit": 4}

DECLARATION = re.compile(r"^\s*(!S_[A-Z0-9_]+)\s*=\s*\$([0-9A-Fa-f]+)\s*(?:;(.*))?$")

STUB_BYTES = 4

SCRATCH = "!S_SCRATCH"

SCRATCH_END = "!S_SCRATCH_END"

EXPLICIT = {"!S_MVN": STUB_BYTES}


def fields(text: str) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        match = DECLARATION.match(line)
        if not match:
            continue
        name, digits, comment = match.group(1), match.group(2), match.group(3) or ""
        at = int(digits, 16)
        if at >= PAGE:
            continue
        width = EXPLICIT.get(name, 1)
        if name not in EXPLICIT:
            for phrase, bytes_wide in WIDTHS.items():
                if phrase in comment:
                    width = bytes_wide
        found[name] = (at, width)
    stops = found.pop(SCRATCH_END, (PAGE, 0))[0]
    if SCRATCH in found:
        found[SCRATCH] = (found[SCRATCH][0], stops - found[SCRATCH][0])
    return found


def overlaps(declared: dict[str, tuple[int, int]]) -> list[tuple[str, str, int]]:
    ordered = sorted(declared.items(), key=lambda one: (one[1][0], one[0]))
    found: list[tuple[str, str, int]] = []
    for index, (name, (at, width)) in enumerate(ordered):
        for other, (other_at, other_width) in ordered[index + 1 :]:
            first = max(at, other_at)
            if first < min(at + width, other_at + other_width):
                found.append((name, other, first))
    return found
