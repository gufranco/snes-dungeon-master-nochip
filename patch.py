"""Redirect every access to the DSP-2 at the code that replaces it.

The image arrives with the routines and the stubs already assembled into filler
that no tour ever read. What remains is to point the cartridge's own
instructions at them, and every replacement is the same width as the
instruction it replaces, so nothing in the image moves and no address the game
computes for itself changes meaning.

    STA $3F8000     four bytes    JSL dsp_write        four bytes
    LDA $3F8000     four bytes    JSL dsp_read         four bytes
    LDA $3FC000     four bytes    LDA #$00 : NOP : NOP four bytes
    MVN $3F,$7E     three bytes   JSR to a stub in the same bank
    MVN $7E,$3F     three bytes   JSR to a stub in the same bank
    JSR $0084       three bytes   JSR to a stub in the same bank

The first write of all is the exception. The boot code sends the sync command
six times, and sync produces nothing, so the first of the six becomes a call
that puts the state block in order before passing the byte on. That is the
earliest point in the run where the processor is in native mode with the data
bank and the direct page already set.

The status poll is answered with zero rather than left to read whatever sits at
that address. Under an emulator that address falls through to a ROM mirror
holding a byte that happens to clear the mask, so the loop happens to exit; that
is an accident of the image's contents and not something to inherit.
"""

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sites

JSL = 0x22
LDA_IMMEDIATE = 0xA9
NOP = 0xEA

STATUS_REPLACEMENT = bytes([LDA_IMMEDIATE, 0x00, NOP, NOP])

BOOT_WRITE = "b00_first"

REQUIRED = (
    "b00_first",
    "b00_feed",
    "b00_drain",
    "b04_0080",
    "b04_0084",
    "b04_0088",
    "b04_008C",
    "dsp_write",
    "dsp_read",
)

STUB_FOR_TRAMPOLINE = {
    0x0080: "b04_0080",
    0x0084: "b04_0084",
    0x0088: "b04_0088",
    0x008C: "b04_008C",
}


class MissingSymbol(Exception):
    pass


class UnknownSite(Exception):
    pass


def read_symbols(text: str) -> dict[str, tuple[int, int]]:
    """The labels asar emitted, as name to bank and address."""
    found = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("["):
            continue
        where, _, name = line.partition(" ")
        name = name.strip()
        if not name or name.startswith(":"):
            continue
        bank, _, address = where.partition(":")
        try:
            found[name] = (int(bank, 16), int(address, 16))
        except ValueError:
            continue
    return found


def resolve(symbols: Mapping[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    """The labels the patch needs, refusing to guess at any it cannot find."""
    absent = [name for name in REQUIRED if name not in symbols]
    if absent:
        raise MissingSymbol(f"the assembled image declares no {', '.join(absent)}")
    return {name: symbols[name] for name in REQUIRED}


def long_call(bank: int, address: int) -> bytes:
    """The bytes of a JSL, which is as wide as the long store it replaces."""
    return bytes([JSL, address & 0xFF, (address >> 8) & 0xFF, bank & 0xFF])


def rewrite_site(
    image: bytearray,
    site: Any,
    symbols: Mapping[str, tuple[int, int]],
    boot: bool = False,
) -> bytearray:
    """Point one site at the code that replaces it."""
    if site.kind == sites.KIND_WRITE:
        target = symbols[BOOT_WRITE] if boot else symbols["dsp_write"]
        image[site.offset : site.offset + 4] = long_call(*target)
    elif site.kind == sites.KIND_READ:
        image[site.offset : site.offset + 4] = long_call(*symbols["dsp_read"])
    elif site.kind == sites.KIND_STATUS:
        image[site.offset : site.offset + 4] = STATUS_REPLACEMENT
    elif site.kind == sites.KIND_FEED:
        image[site.offset : site.offset + 3] = sites.call_to(symbols["b00_feed"][1])
    elif site.kind == sites.KIND_DRAIN:
        image[site.offset : site.offset + 3] = sites.call_to(symbols["b00_drain"][1])
    else:
        raise UnknownSite(
            f"{site.kind} is not a site this knows how to rewrite, so the image would"
            " have been returned with that access still going to the chip"
        )
    return image


def apply(
    image: bytes | bytearray,
    symbols: Mapping[str, tuple[int, int]],
    boot_write_offset: int | None = None,
) -> bytes:
    """Every site redirected, in one pass over a copy of the image."""
    found = sites.find(image)
    if boot_write_offset is None:
        writes = [site for site in found if site.kind == sites.KIND_WRITE]
        boot_write_offset = writes[0].offset if writes else None

    patched = bytearray(image)
    for site in found:
        rewrite_site(patched, site, symbols, boot=site.offset == boot_write_offset)

    for call in sites.find_trampoline_calls(image):
        stub = symbols[STUB_FOR_TRAMPOLINE[call.trampoline]]
        patched[call.offset : call.offset + 3] = sites.call_to(stub[1])

    return bytes(patched)


WIDTHS = {
    sites.KIND_WRITE: 4,
    sites.KIND_READ: 4,
    sites.KIND_STATUS: 4,
    sites.KIND_FEED: 3,
    sites.KIND_DRAIN: 3,
}


def regions(image: bytes | bytearray) -> set[int]:
    """Every byte the patch is entitled to alter.

    A replacement is the same width as the instruction it replaces, so this is
    also the complete set of bytes that may differ afterwards. Some of them will
    not: a near call keeps the opcode of the near call it replaces, and the
    answer to the status poll keeps a zero. Counting altered bytes would
    therefore report fewer than this and prove nothing, whereas an alteration
    outside this set is a defect whatever its size.
    """
    covered: set[int] = set()
    for site in sites.find(image):
        covered.update(range(site.offset, site.offset + WIDTHS[site.kind]))
    for call in sites.find_trampoline_calls(image):
        covered.update(range(call.offset, call.offset + 3))
    return covered


def residue(image: bytes | bytearray) -> dict[str, int]:
    """Any retail access the patch failed to redirect."""
    left = sites.census(sites.find(image))
    return {kind: count for kind, count in left.items() if count}
