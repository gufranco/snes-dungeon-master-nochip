import re
import sys
from collections import namedtuple
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import script

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import assembled  # noqa: E402
import hardware  # noqa: E402
import patch  # noqa: E402
import sites  # noqa: E402

hardware.install()

from romimage import rewrite  # noqa: E402

FILLER = (
    ("routines", "ROUTINES", "routines_end"),
    ("bank 00 stubs", "BANK00", "bank00_end"),
    ("bank 04 stubs", "BANK04", "bank04_end"),
)

HEADER_FIELDS = (
    rewrite.CHIPSET,
    rewrite.ROM_SIZE,
    rewrite.CHECKSUM_COMPLEMENT,
    rewrite.CHECKSUM_COMPLEMENT + 1,
    rewrite.CHECKSUM,
    rewrite.CHECKSUM + 1,
)

DEFINE = re.compile(r"^\s*!(\w+)\s*=\s*\$([0-9A-Fa-f]+)")

EXAMPLE_LIMIT = 8

Report = namedtuple("Report", "differ counted loose")


class NoRegion(Exception):
    pass


def _ok(self: Any) -> bool:
    found: bool = not self.loose
    return found


Report.ok = property(_ok)  # type: ignore[attr-defined]


def defines(text: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for line in text.splitlines():
        match = DEFINE.match(line)
        if match:
            found[match.group(1)] = int(match.group(2), 16)
    return found


def bank_and_address(value: int) -> tuple[int, int]:
    return (value >> 16, value & 0xFFFF)


def filler(text: str, symbols: Mapping[str, tuple[int, int]]) -> dict[str, set[int]]:
    declared = defines(text)
    found: dict[str, set[int]] = {}
    for name, base, end in FILLER:
        if base not in declared:
            raise NoRegion(f"the assembly declares no !{base}")
        if end not in symbols:
            raise NoRegion(f"the label table declares no {end}")
        start = sites.offset_of(*bank_and_address(declared[base]))
        stop = sites.offset_of(*symbols[end])
        if stop < start:
            raise NoRegion(f"{end} sits before !{base}")
        found[name] = set(range(start, stop))
    return found


def header(image: bytes | bytearray) -> set[int]:
    covered: set[int] = set()
    for at in rewrite.mirrors(image):
        covered.update(at + field for field in HEADER_FIELDS)
    return covered


def claims(
    retail: bytes | bytearray,
    text: str,
    symbols: Mapping[str, tuple[int, int]],
) -> dict[str, set[int]]:
    found = filler(text, symbols)
    found["redirected sites"] = patch.regions(retail)
    found["header"] = header(retail)
    return found


def differences(retail: bytes | bytearray, final: bytes | bytearray) -> list[int]:
    if len(retail) != len(final):
        raise NoRegion(f"the images are {len(retail):,} and {len(final):,} bytes")
    return [at for at in range(len(retail)) if retail[at] != final[at]]


def account(
    retail: bytes | bytearray,
    final: bytes | bytearray,
    text: str,
    symbols: Mapping[str, tuple[int, int]],
) -> Any:
    entitled = claims(retail, text, symbols)
    counted: dict[str, int] = {}
    loose: list[int] = []
    for at in differences(retail, final):
        for name, where in entitled.items():
            if at in where:
                counted[name] = counted.get(name, 0) + 1
                break
        else:
            loose.append(at)
    return Report(differ=sum(counted.values()) + len(loose), counted=counted, loose=loose)


def explain(report: Any, retail: bytes | bytearray, final: bytes | bytearray) -> str:
    lines = [f"  {report.differ:,} bytes differ from the dump"]
    for name, count in sorted(report.counted.items(), key=lambda one: -one[1]):
        lines.append(f"      {name:<18} {count:,}")
    if not report.loose:
        lines.append("  every one of them is inside a region something declared")
        return "\n".join(lines)

    lines.append(f"  {len(report.loose):,} belong to no declared region:")
    for at in report.loose[:EXAMPLE_LIMIT]:
        bank, address = sites.address_of(at)
        lines.append(
            f"      ${at:06X}  ${bank:02X}:{address:04X}  {retail[at]:#04x} -> {final[at]:#04x}"
        )
    if len(report.loose) > EXAMPLE_LIMIT:
        lines.append(f"      and {len(report.loose) - EXAMPLE_LIMIT:,} more")
    return "\n".join(lines)


def main(argv: list[str], say: Callable[[str], None] = print) -> int:
    if len(argv) != 3:
        say("usage: similarity.py <retail dump> <finished cartridge>")
        return 2

    reason = assembled.stale()
    if reason is not None:
        say(f"  {reason}")
        return 2

    retail = Path(argv[1]).read_bytes()
    final = Path(argv[2]).read_bytes()
    report = account(
        retail,
        final,
        assembled.ASSEMBLY.read_text(),
        patch.read_symbols(assembled.SYMBOLS.read_text()),
    )
    say(explain(report, retail, final))
    return 0 if report.ok else 1


script.entry(__name__, main, sys.argv)
