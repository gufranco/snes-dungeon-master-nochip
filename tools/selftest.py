"""Drive the software chip on a real processor and check every byte it returns.

The benchmark only ever ran two of the six commands, because those two are what
the cartridge spends its time on. The other four were assembled, read, and never
executed, and the converted image went dark the moment the game reached the
dungeon and used them.

This builds a script of cases, compiles it into a cartridge that walks them
through the same entry points the patched game calls, and compares what the
routines return against the model that reproduced seventy-two million bytes of
recorded cartridge traffic. Cases come from that recorded traffic wherever
possible, so what is checked is what the game actually asks for.

The script is a byte stream the cartridge at asm/dsp2-selftest.asm walks:

    $01 lo hi <n bytes>   feed these n bytes to the chip
    $02 lo hi             read n bytes back and record them
    $00                   the script is finished
"""

from collections import namedtuple
from pathlib import Path

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


def _model():
    """The vendored coprocessor model, imported rather than read off disk."""
    import sys

    sys.path.insert(0, str(ROOT))
    import hardware

    hardware.install()
    import snesdsp

    return snesdsp


def output_size(command, lengths):
    """How many bytes the command hands back, from its own declaration.

    Reading until the port goes idle would stop early on any output that
    legitimately contains the idle byte, so the size comes from the command
    rather than from the answer.
    """
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


def new_chip():
    """A model in the state a cartridge is in before its first command."""
    return _model().Chip()


def case_for(command, lengths, payload, chip=None):
    """One case, with the answer taken from the model rather than assumed.

    The chip carries state between commands: the transparent colour set by one
    command decides what a later merge returns. A case built against a fresh
    model would therefore be answered differently from the same case in a run,
    so the caller passes the model it is walking and the cases stay in step.
    """
    if chip is None:
        chip = new_chip()
    feed = bytes([command, *lengths, *payload])
    for byte in feed:
        chip.write(byte)
    wanted = output_size(command, lengths)
    produced = bytes(chip.read() for _ in range(wanted))
    return Case(feed, wanted, produced)


def cases_for(transactions):
    """A run of cases walked through one model, in the order given."""
    chip = new_chip()
    return [case_for(command, lengths, payload, chip) for command, lengths, payload in transactions]


def build_script(cases):
    """The byte stream the cartridge walks."""
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


def expected(cases):
    """Every byte the cases should hand back, in order."""
    return b"".join(case.output for case in cases)


def compare(cases, produced):
    """Where the run and the model disagree, by case and by position."""
    wanted = expected(cases)
    found = []
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
