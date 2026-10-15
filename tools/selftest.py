from collections import namedtuple
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

FEED = 0x01
DRAIN = 0x02
END = 0x00

SCRIPT_BANK_BYTES = 0x8000

COMMAND_TILE = 0x01
COMMAND_TRANSPARENT = 0x03
COMMAND_MERGE = 0x05
COMMAND_MIRROR = 0x06
COMMAND_MULTIPLY = 0x09
COMMAND_SCALE = 0x0D
COMMAND_SYNC = 0x0F

Case = namedtuple("Case", "feed reads output", defaults=(b"",))


class ScriptTooLong(Exception):
    pass


def _model() -> Any:
    import sys

    sys.path.insert(0, str(ROOT))
    import hardware

    hardware.install()
    import snesdsp

    return snesdsp


def output_size(command: int, lengths: tuple[int, ...]) -> int:
    if command == COMMAND_MERGE:
        return lengths[0]
    if command == COMMAND_MIRROR:
        return lengths[0]
    if command == COMMAND_SCALE:
        return lengths[1]
    if command == COMMAND_TILE:
        return 32
    if command == COMMAND_MULTIPLY:
        return 4
    return 0


PART = "dsp2"


def new_chip(model: Any = None) -> Any:
    return (model or _model()).Chip(PART)


def why_not(model: Any = None) -> Any:
    return (model or _model()).why_not()


def case_for(
    command: int,
    lengths: tuple[int, ...],
    payload: bytes,
    chip: Any = None,
    build: Any = new_chip,
) -> Any:
    if chip is None:
        chip = build()
    feed = bytes([command, *lengths, *payload])
    for byte in feed:
        chip.write(byte)
    wanted = output_size(command, lengths)
    produced = bytes(chip.read() for _ in range(wanted))
    return Case(feed, wanted, produced)


def cases_for(transactions: Any, build: Any = new_chip) -> list[Any]:
    chip = build()
    return [case_for(command, lengths, payload, chip) for command, lengths, payload in transactions]


def build_script(cases: Any) -> bytes:
    out = bytearray()
    for case in cases:
        if case.feed:
            out.append(FEED)
            out += len(case.feed).to_bytes(2, "little")
            out += case.feed
        if case.reads:
            out.append(DRAIN)
            out += case.reads.to_bytes(2, "little")
    out.append(END)
    if len(out) > SCRIPT_BANK_BYTES:
        raise ScriptTooLong(
            f"the script is {len(out)} bytes and the bank holds {SCRIPT_BANK_BYTES}"
        )
    return bytes(out)


def expected(cases: Any) -> bytes:
    return b"".join(case.output for case in cases)


def compare(cases: Any, produced: bytes) -> list[Any]:
    wanted = expected(cases)
    found: list[tuple[int, int, Any, Any]] = []
    at = 0
    for index, case in enumerate(cases):
        for step in range(case.reads):
            if at >= len(produced):
                found.append((index, step, case.output[step], None))
            elif produced[at] != case.output[step]:
                found.append((index, step, case.output[step], produced[at]))
            at += 1
    if len(produced) > len(wanted):
        found.append((len(cases), 0, None, produced[len(wanted)]))
    return found
