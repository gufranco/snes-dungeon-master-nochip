from collections import namedtuple
from collections.abc import Sequence
from typing import Any

STA_PORT = bytes([0x8F, 0x00, 0x80, 0x3F])
LDA_PORT = bytes([0xAF, 0x00, 0x80, 0x3F])
LDA_STATUS = bytes([0xAF, 0x00, 0xC0, 0x3F])
MVN_TO_PORT = bytes([0x54, 0x3F, 0x7E])
MVN_FROM_PORT = bytes([0x54, 0x7E, 0x3F])

BANK_SIZE = 0x8000
BANK_WINDOW = 0x8000

KIND_WRITE = "write"
KIND_READ = "read"
KIND_STATUS = "status"
KIND_FEED = "feed"
KIND_DRAIN = "drain"

SIGNATURES = {
    KIND_WRITE: STA_PORT,
    KIND_READ: LDA_PORT,
    KIND_STATUS: LDA_STATUS,
    KIND_FEED: MVN_TO_PORT,
    KIND_DRAIN: MVN_FROM_PORT,
}

EXPECTED = {
    "USA": {
        KIND_WRITE: 51,
        KIND_READ: 4,
        KIND_STATUS: 5,
        KIND_FEED: 16,
        KIND_DRAIN: 2,
    }
}

TRAMPOLINES = (0x0080, 0x0084, 0x0088, 0x008C)

TRAMPOLINE_BANK = 0x04

EXPECTED_TRAMPOLINE_CALLS = {0x0080: 2, 0x0084: 5, 0x0088: 4, 0x008C: 1}

JSR = 0x20

Site = namedtuple("Site", "kind offset address bank")
TrampolineCall = namedtuple("TrampolineCall", "offset address bank trampoline")


class UnexpectedImage(Exception):
    pass


def address_of(offset: int) -> tuple[int, int]:
    return (offset // BANK_SIZE, BANK_WINDOW + (offset % BANK_SIZE))


def offset_of(bank: int, address: int) -> int:
    return (bank & 0x7F) * BANK_SIZE + (address - BANK_WINDOW)


def occurrences(image: bytes | bytearray, pattern: bytes) -> list[int]:
    found: list[Any] = []
    at = image.find(pattern)
    while at >= 0:
        found.append(at)
        at = image.find(pattern, at + 1)
    return found


def find(image: bytes | bytearray, kinds: Sequence[str] | None = None) -> list[Site]:
    wanted = SIGNATURES if kinds is None else {kind: SIGNATURES[kind] for kind in kinds}
    found: list[Any] = []
    for kind, pattern in wanted.items():
        for offset in occurrences(image, pattern):
            bank, address = address_of(offset)
            found.append(Site(kind, offset, address, bank))
    return sorted(found, key=lambda site: site.offset)


def census(sites: Sequence[Site]) -> dict[str, int]:
    counted = dict.fromkeys(SIGNATURES, 0)
    for site in sites:
        counted[site.kind] += 1
    return counted


def verify(sites: Sequence[Site], region: str = "USA") -> dict[str, int]:
    if region not in EXPECTED:
        raise UnexpectedImage(
            f"no measured site counts for region {region}; measured regions are {sorted(EXPECTED)}"
        )
    wanted = EXPECTED[region]
    found = census(sites)
    wrong = {kind: (wanted[kind], found[kind]) for kind in wanted if wanted[kind] != found[kind]}
    if wrong:
        detail = ", ".join(
            f"{kind} expected {want} found {got}" for kind, (want, got) in sorted(wrong.items())
        )
        raise UnexpectedImage(f"access surface does not match region {region}: {detail}")
    return found


def banks_touched(sites: Sequence[Site]) -> list[int]:
    return sorted({site.bank for site in sites})


def call_to(address: int) -> bytes:
    return bytes([JSR, address & 0xFF, (address >> 8) & 0xFF])


def find_trampoline_calls(
    image: bytes | bytearray, bank: int = TRAMPOLINE_BANK
) -> list[TrampolineCall]:
    found: list[Any] = []
    start = (bank & 0x7F) * BANK_SIZE
    for trampoline in TRAMPOLINES:
        pattern = call_to(trampoline)
        for offset in occurrences(image[start : start + BANK_SIZE], pattern):
            at = start + offset
            found.append(TrampolineCall(at, address_of(at)[1], bank, trampoline))
    return sorted(found, key=lambda call: call.offset)


def verify_trampoline_calls(calls: Sequence[TrampolineCall]) -> dict[int, int]:
    found = dict.fromkeys(TRAMPOLINES, 0)
    for call in calls:
        found[call.trampoline] += 1
    if found != EXPECTED_TRAMPOLINE_CALLS:
        detail = ", ".join(
            f"${where:04X} expected {want} found {found[where]}"
            for where, want in sorted(EXPECTED_TRAMPOLINE_CALLS.items())
            if found[where] != want
        )
        raise UnexpectedImage(f"trampoline traffic does not match: {detail}")
    return found
