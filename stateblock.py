"""That no two fields of the state block share a byte.

The chip kept its state inside itself. The replacement keeps it in a page of
work RAM, laid out by hand as a list of offsets in the assembly, and nothing
checks that list against itself. The assembler will not: an offset is a number,
and two names for one number assemble without complaint.

Two of them did share. `!S_OVERLAY` was declared at $0E, which is `!S_INBYTE`,
and the sixteen bit store that sets it reached into $0F, which is
`!S_XFER_BANK`. That field carries the bank a block transfer reads from, and a
transfer that has to split re-reads it after the operation runs, so a merge
would have taken its next chunk from whatever bank the overlay pointer's high
byte happened to be. It never fired, because no transfer in any recording
splits, which is exactly what makes it worth a check rather than a reading.

The widths come from what each line says about itself. A field the assembly
calls sixteen bit is two bytes and one it calls twenty four bit is three; a line
that says nothing is one byte, which is what the eight bit fields are.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SOURCE = ROOT / "asm" / "dsp2-state.asm"

PAGE = 0x100
"""How far the block reaches, which is the direct page the routines point at."""

WIDTHS = {"16 bit": 2, "24 bit": 3, "32 bit": 4}
"""What a line saying so about itself declares, in bytes."""

DECLARATION = re.compile(r"^\s*(!S_[A-Z0-9_]+)\s*=\s*\$([0-9A-Fa-f]+)\s*(?:;(.*))?$")

STUB_BYTES = 4
"""The block move stub, which is an instruction rather than a value."""

SCRATCH = "!S_SCRATCH"

SCRATCH_END = "!S_SCRATCH_END"
"""Where the operations' working room stops, when anything is declared above it.

Without this the region is taken to run to the end of the page, which is what it
did until a field wanted a home that had to survive between operations. It is a
boundary rather than a field, so it is read and then dropped.
"""

EXPLICIT = {"!S_MVN": STUB_BYTES}
"""Fields whose width is not something a line about them would say.

The scratch region is the other one, and its width depends on where it starts,
so it is filled in once the offsets are read. Leaving it a single byte would let
a field be declared inside the room the operations work in, which is how the
merge tables' validity marker came to sit eight bytes into it.
"""


def fields(text: str) -> dict[str, tuple[int, int]]:
    """Every field the block declares, as name to offset and width."""
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
    """Every pair of fields that share a byte, with the first byte they share."""
    ordered = sorted(declared.items(), key=lambda one: (one[1][0], one[0]))
    found: list[tuple[str, str, int]] = []
    for index, (name, (at, width)) in enumerate(ordered):
        for other, (other_at, other_width) in ordered[index + 1 :]:
            first = max(at, other_at)
            if first < min(at + width, other_at + other_width):
                found.append((name, other, first))
    return found
