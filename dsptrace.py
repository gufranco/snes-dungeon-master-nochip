import struct
from collections import Counter, namedtuple
from itertools import pairwise
from pathlib import Path

RECORD_BYTES = 28
RECORD = struct.Struct("<IIHHBB8sBB4s")

KIND_WRITE = 0
KIND_READ = 1

DSP_BANK = 0x3F
WRAM_BANKS = (0x7E, 0x7F)

MVN = 0x54
MVP = 0x44

COMMAND_SYNC = 0x0F
COMMAND_TILE = 0x01
COMMAND_TRANSPARENT = 0x03
COMMAND_MERGE = 0x05
COMMAND_MIRROR = 0x06
COMMAND_MULTIPLY = 0x09
COMMAND_SCALE = 0x0D

FIXED_INPUT = {
    COMMAND_TILE: 32,
    COMMAND_TRANSPARENT: 1,
    COMMAND_MULTIPLY: 4,
}

FIXED_OUTPUT = {
    COMMAND_TILE: 32,
    COMMAND_MULTIPLY: 4,
}

LENGTH_PREFIXED = {COMMAND_MERGE, COMMAND_MIRROR, COMMAND_SCALE}

COMMAND_NAMES = {
    COMMAND_TILE: "tile",
    COMMAND_TRANSPARENT: "transparent",
    COMMAND_MERGE: "merge",
    COMMAND_MIRROR: "mirror",
    COMMAND_MULTIPLY: "multiply",
    COMMAND_SCALE: "scale",
    COMMAND_SYNC: "sync",
}

Record = namedtuple(
    "Record",
    "frame pc x y kind byte dbr p move_source_bank move_destination_bank",
)
Summary = namedtuple(
    "Summary",
    "total complete incomplete per_command sites sources source_banks lengths",
)


class TruncatedTrace(Exception):
    pass


class UnknownLength(Exception):
    pass


def is_work_ram(bank):
    return bank in WRAM_BANKS


class Transaction:
    def __init__(self, frame, pc, command):
        self.frame = frame
        self.pc = pc
        self.command = command
        self.lengths = ()
        self.parameters = b""
        self.output = b""
        self.source = None
        self.second_source = None
        self.strides = ()
        self.complete = False

    @property
    def name(self):
        return COMMAND_NAMES.get(self.command, f"op{self.command:02X}")

    @property
    def source_banks(self):
        return tuple(where[0] for where in (self.source, self.second_source) if where is not None)

    def __repr__(self):
        where = "" if self.source is None else f" src=${self.source[0]:02X}:{self.source[1]:04X}"
        return (
            f"<{self.name} frame={self.frame} pc=${self.pc:06X} "
            f"in={len(self.parameters)} out={len(self.output)}{where}>"
        )


def records(path):
    with Path(path).open("rb") as handle:
        while True:
            blob = handle.read(RECORD_BYTES)
            if not blob:
                return
            if len(blob) != RECORD_BYTES:
                raise TruncatedTrace(f"{len(blob)} trailing bytes, expected {RECORD_BYTES}")
            frame, pc, x, y, kind, byte, _trampolines, dbr, p, around = RECORD.unpack(blob)
            source_bank = None
            destination_bank = None
            if around[0] in (MVN, MVP):
                destination_bank = around[1]
                source_bank = around[2]
            yield Record(
                frame=frame,
                pc=pc,
                x=x,
                y=y,
                kind=kind,
                byte=byte,
                dbr=dbr,
                p=p,
                move_source_bank=source_bank,
                move_destination_bank=destination_bank,
            )


class _Run:
    def __init__(self):
        self.segments = []

    def note(self, record):
        if record.move_source_bank is None:
            self.segments.append(None)
            return
        key = (record.move_source_bank, record.x)
        if self.segments and self.segments[-1] is not None:
            bank, address = self.segments[-1][0], self.segments[-1][1]
            if bank == record.move_source_bank and record.x == (
                (address + self.segments[-1][2]) & 0xFFFF
            ):
                self.segments[-1] = (bank, address, self.segments[-1][2] + 1)
                return
        self.segments.append((key[0], key[1], 1))

    def _blocks(self):
        return [segment for segment in self.segments if segment is not None]

    def sources(self):
        blocks = self._blocks()
        if not blocks:
            return None, None
        first = (blocks[0][0], blocks[0][1])
        second = None
        for bank, address, _ in blocks[1:]:
            if bank != first[0]:
                second = (bank, address)
                break
        return first, second

    def strides(self):
        blocks = self._blocks()
        gaps = set()
        for previous, current in pairwise(blocks):
            if previous[0] != current[0]:
                continue
            gaps.add((current[1] - previous[1]) & 0xFFFF)
        return tuple(sorted(gaps))


def transactions(stream):
    pending = None
    run = None
    wanted_in = 0
    wanted_out = 0
    stage = 0

    for record in stream:
        if pending is None:
            if record.kind != KIND_WRITE:
                continue
            pending = Transaction(record.frame, record.pc, record.byte)
            run = _Run()
            stage = 0
            command = record.byte

            if command in LENGTH_PREFIXED:
                wanted_in = 2 if command == COMMAND_SCALE else 1
                wanted_out = 0
                stage = 1
            else:
                wanted_in = FIXED_INPUT.get(command, 0)
                wanted_out = FIXED_OUTPUT.get(command, 0)

            if wanted_in == 0 and wanted_out == 0:
                pending.complete = True
                yield pending
                pending = None
            continue

        if record.kind == KIND_WRITE:
            if stage == 1:
                pending.lengths = (*pending.lengths, record.byte)
                wanted_in -= 1
                if wanted_in == 0:
                    stage = 2
                    wanted_in, wanted_out = _payload_sizes(pending.command, pending.lengths)
                    if wanted_in == 0:
                        pending.complete = True
                        yield pending
                        pending = None
                continue

            pending.parameters += bytes([record.byte])
            run.note(record)
            wanted_in -= 1
            if wanted_in == 0 and wanted_out == 0:
                _finish(pending, run)
                yield pending
                pending = None
            continue

        if wanted_in > 0:
            continue

        pending.output += bytes([record.byte])
        wanted_out -= 1
        if wanted_out == 0:
            _finish(pending, run)
            yield pending
            pending = None

    if pending is not None:
        _finish(pending, run, complete=False)
        yield pending


def _finish(transaction, run, complete=True):
    transaction.source, transaction.second_source = run.sources()
    transaction.strides = run.strides()
    transaction.complete = complete


def _payload_sizes(command, lengths):
    """How much a command takes and gives once its lengths are known.

    Only the three commands that declare a length ever reach here, because only
    those put the stream into the stage that asks. A fourth would mean a command
    was given a length nobody wrote a rule for, so it says so rather than
    answering nothing and quietly finishing the transaction early.
    """
    if command == COMMAND_MERGE:
        return 2 * lengths[0], lengths[0]
    if command == COMMAND_MIRROR:
        return lengths[0], lengths[0]
    if command == COMMAND_SCALE:
        return (lengths[0] + 1) >> 1, (lengths[1] + 1) >> 1
    raise UnknownLength(f"{command:#04x} was given a length and declares none")


def summarise(stream):
    total = 0
    complete = 0
    per_command = Counter()
    sites = Counter()
    sources = Counter()
    source_banks = Counter()
    lengths = Counter()

    for transaction in stream:
        total += 1
        complete += 1 if transaction.complete else 0
        per_command[transaction.command] += 1
        sites[transaction.pc] += 1
        for where in (transaction.source, transaction.second_source):
            if where is not None:
                sources[(transaction.command, *where)] += 1
                source_banks[(transaction.command, where[0])] += 1
        if transaction.lengths:
            lengths[(transaction.command, *transaction.lengths)] += 1

    return Summary(
        total=total,
        complete=complete,
        incomplete=total - complete,
        per_command=per_command,
        sites=sites,
        sources=sources,
        source_banks=source_banks,
        lengths=lengths,
    )


def report(summary):
    lines = [f"  transactions {summary.total:,}, incomplete {summary.incomplete:,}"]
    for command, count in sorted(summary.per_command.items()):
        name = COMMAND_NAMES.get(command, f"op{command:02X}")
        lines.append(f"    ${command:02X} {name:<12s} {count:>10,}")

    lines.append(f"  issuing sites {len(summary.sites)}")
    for pc, count in sorted(summary.sites.items()):
        lines.append(f"    ${pc:06X}  {count:>10,}")

    lines.append("  source banks, by command")
    for (command, bank), count in sorted(summary.source_banks.items()):
        name = COMMAND_NAMES.get(command, f"op{command:02X}")
        where = "work RAM" if is_work_ram(bank) else "ROM"
        lines.append(f"    ${command:02X} {name:<12s} bank ${bank:02X} {where:<9s} {count:>10,}")

    lines.append(f"  distinct source addresses {len(summary.sources):,}")
    lines.append(f"  distinct length tuples {len(summary.lengths):,}")
    return "\n".join(lines)
