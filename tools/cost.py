"""What each command costs once it is code, measured on the processor model.

The chip answered in parallel with the program that asked it, so from the
cartridge's point of view a command cost only the bytes it pushed through the
port. Replacing the chip with code moves that work onto the same processor the
game runs on, and whether the conversion is worth having depends on a number:
how many cycles the replacement spends against how many the retail path spent.

Both sides are counted rather than argued. The replacement runs on the 65816
model, which drives a bus cycle by cycle, so its cost is the cycles it actually
took. The retail cost is derived from the accesses the recorded trace shows the
cartridge making, priced at what the processor charges for each: a long store or
load is five cycles and a block move is seven a byte.

A command that costs more than the retail path is a regression the conversion
has to answer for, so the comparison is printed per command rather than summed
into one figure that would hide it.
"""

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hardware  # noqa: E402

mos65xx = hardware.load("mos65xx")

MODEL = "65816"
"""The part this cartridge runs, named because the family covers sixteen of them."""

BANK = 0x8000
WRAM = 0x20000

O_BUFFER = 0x000C00

LONG_ACCESS_CYCLES = 5
"""A load or store through a twenty four bit address, which is how the port was reached."""

MOVE_CYCLES_PER_BYTE = 7
"""What a block move charges for each byte, which is how payloads were delivered."""

RETURN = 0x00FFFF
"""Where a measured call is told to return to, so the run ends on a known fetch."""

DECLARED_LENGTHS = {
    "sync": 0,
    "tile": 0,
    "transparent": 0,
    "multiply": 0,
    "merge": 1,
    "mirror": 1,
    "scale": 2,
}
"""How many length bytes each command sends before its payload."""


class Ran(Exception):
    pass


class LoRom:
    """The cartridge as the processor sees it, with work RAM behind it.

    Only what a measured routine touches is modelled: the cartridge read through
    the LoROM window, work RAM, and the processor's own multiplier. An access to
    anything else raises rather than returning a plausible byte, because a
    routine reading a register this does not model would otherwise be measured
    against a fabricated answer.
    """

    def __init__(self, rom: bytes) -> None:
        self.rom = rom
        self.wram = bytearray(WRAM)
        self.multiplicand = 0
        self.multiplier = 0

    def _product(self) -> int:
        return (self.multiplicand * self.multiplier) & 0xFFFF

    def read8(self, address: int) -> int:
        bank, offset = (address >> 16) & 0xFF, address & 0xFFFF
        if bank in (0x7E, 0x7F):
            return self.wram[((bank & 1) << 16) | offset]
        if bank in (0x00, 0x80) and offset < 0x2000:
            return self.wram[offset]
        if offset == 0x4216:
            return self._product() & 0xFF
        if offset == 0x4217:
            return (self._product() >> 8) & 0xFF
        if offset >= BANK:
            return self.rom[((bank & 0x7F) * BANK + (offset - BANK)) % len(self.rom)]
        raise Ran(f"read of ${address:06X}, which this harness does not model")

    def write8(self, address: int, value: int) -> None:
        bank, offset = (address >> 16) & 0xFF, address & 0xFFFF
        if bank in (0x7E, 0x7F):
            self.wram[((bank & 1) << 16) | offset] = value
            return
        if bank in (0x00, 0x80) and offset < 0x2000:
            self.wram[offset] = value
            return
        if offset == 0x4202:
            self.multiplicand = value
            return
        if offset == 0x4203:
            self.multiplier = value
            return
        if offset in (0x420B, 0x420C, 0x420D):
            return
        raise Ran(f"write of ${address:06X}, which this harness does not model")


def symbols(text: str) -> dict[str, int]:
    """The labels the assembler emitted, as name to a twenty four bit address."""
    found: dict[str, int] = {}
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
            found[name] = (int(bank, 16) << 16) | int(address, 16)
        except ValueError:
            continue
    return found


def retail_cost(command: str, parameters: bytes, output: bytes) -> int:
    """What the same exchange cost the cartridge when a chip answered it.

    One long store carries the command byte, one carries each length the command
    declares, the payload goes in by block move and the result comes back the
    same way. The status poll is not counted: it was a loop whose length depended
    on the chip, and counting a guess would flatter whichever side it was added to.
    """
    stores = 1 + DECLARED_LENGTHS.get(command, 0)
    return stores * LONG_ACCESS_CYCLES + (len(parameters) + len(output)) * MOVE_CYCLES_PER_BYTE


def stale(symbols_path: Path, rom_path: Path) -> bool:
    """Whether the symbol table describes an older image than the one being measured.

    The assembler emits the image and the table on separate passes, so a build
    that ran without the second one leaves a table naming where every routine
    used to be. Entered at those addresses the first routine runs off into the
    stack and reports that it never returned, which reads as a fault in the code
    rather than in the table it was found through.
    """
    return symbols_path.stat().st_mtime < rom_path.stat().st_mtime


def machine(rom: bytes) -> tuple[Any, LoRom]:
    """A processor with the cartridge behind it, in native mode."""
    memory = LoRom(rom)
    cpu = mos65xx.Cpu(MODEL, memory)
    cpu.reset()
    cpu.set_emulation(False)
    return cpu, memory


def enter(cpu: Any, address: int, limit: int = 4_000_000) -> int:
    """Cycles spent in one call, entered so that its own return ends the run.

    A return address the harness owns is pushed before the jump, so the routine's
    RTL lands on a place nothing else reaches and the count stops there.
    """
    cpu.s = 0x1FFF
    cpu.d = 0x0000
    cpu.db = 0x00
    cpu.push8((RETURN >> 16) & 0xFF)
    cpu.push16_flat((RETURN - 1) & 0xFFFF)
    cpu.pc = address & 0xFFFF
    cpu.pb = (address >> 16) & 0xFF
    before = cpu.cycles
    for _ in range(limit):
        if ((cpu.pb << 16) | cpu.pc) == RETURN:
            return int(cpu.cycles - before)
        cpu.step()
    raise Ran(f"the routine at ${address:06X} did not return within {limit} steps")


SOURCE = 0x7E4000
"""Where the harness stages a payload, standing in for the game's own buffer."""

DESTINATION = 0x7E5000
"""Where the harness drains a result to, standing in for the game's own buffer."""


TRAMPOLINE = 0x0084
"""The work RAM block mover this prices the dispatched path through.

The cartridge reaches the chip two ways. Eighteen sites in bank $00 name their
banks in the instruction and become a call straight to a transfer. The rest go
through one of four block movers the boot code installs in work RAM, whose bank
operands the caller writes first, and those became dispatchers that read the
operands back and decide from them. Measured across a tour, 24 of the 40 million
port transactions arrive that way, so pricing only the direct path understates
what most of the traffic costs.
"""

DISPATCHED = "tramp_0084"

DESTINATION_OPERAND = TRAMPOLINE + 1
SOURCE_OPERAND = TRAMPOLINE + 2

PORT_BANK = 0x3F
WORK_RAM_BANK = 0x7E


def through(names: dict[str, int], dispatched: bool) -> tuple[int, int]:
    """The entry points a transfer takes, direct or through a dispatcher."""
    if dispatched:
        return names[DISPATCHED], names[DISPATCHED]
    return names["dsp_feed_wram"], names["dsp_drain_wram"]


def point(memory: LoRom, destination: int, source: int) -> None:
    """The operand bytes a dispatcher reads back to decide what it stands in for."""
    memory.write8(DESTINATION_OPERAND, destination)
    memory.write8(SOURCE_OPERAND, source)


def measure(
    cpu: Any,
    memory: LoRom,
    names: dict[str, int],
    command: int,
    lengths: tuple[int, ...],
    payload: bytes,
    output_length: int,
    dispatched: bool = False,
) -> int:
    """Cycles the replacement spends on one whole exchange.

    The exchange is delivered the way the cartridge delivers it: the command and
    the lengths it declares arrive as single stores, and the payload arrives as
    one block move, because those are the two instruction forms the sites carry.
    Measuring the payload a byte at a time would count a path the game does not
    take and charge the replacement for it.
    """
    feed, drain = through(names, dispatched)
    total = 0
    for byte in bytes([command]) + bytes(lengths):
        cpu.set_acc(byte)
        total += enter(cpu, names["dsp_write"])

    if payload:
        memory.wram[SOURCE & 0xFFFF : (SOURCE & 0xFFFF) + len(payload)] = payload
        point(memory, PORT_BANK, WORK_RAM_BANK)
        cpu.m8 = False
        cpu.x8 = False
        cpu.a = len(payload) - 1
        cpu.x = SOURCE & 0xFFFF
        cpu.y = 0x0000
        total += enter(cpu, feed)

    if output_length:
        point(memory, WORK_RAM_BANK, PORT_BANK)
        cpu.m8 = False
        cpu.x8 = False
        cpu.a = output_length - 1
        cpu.x = 0x0000
        cpu.y = DESTINATION & 0xFFFF
        total += enter(cpu, drain)
    return total


def produced(memory: LoRom, length: int) -> bytes:
    """What the replacement drained into the buffer the caller named."""
    at = DESTINATION & 0xFFFF
    return bytes(memory.wram[at : at + length])


def report(rows: dict[str, list[tuple[int, int, int, bool]]], say: Any = print) -> int:
    """One line per command, and a non-zero status when any of them is slower.

    The two columns of ours are the two ways the cartridge reaches the chip. The
    direct one is the eighteen sites in bank $00 that name their banks in the
    instruction; the dispatched one goes through a block mover in work RAM whose
    operands the caller writes first, and most of the traffic goes that way.
    """
    say(
        f"  {'command':<12}{'calls':>7}{'direct':>9}{'dispatched':>12}"
        f"{'retail':>9}{'ratio':>8}  correct"
    )
    slower = 0
    for name in sorted(rows):
        entries = rows[name]
        ours = sum(one for one, _, _, _ in entries) / len(entries)
        dispatched = sum(two for _, two, _, _ in entries) / len(entries)
        theirs = sum(three for _, _, three, _ in entries) / len(entries)
        right = sum(1 for _, _, _, ok in entries if ok)
        ratio = ours / theirs if theirs else 0.0
        if ratio > 1.0:
            slower += 1
        say(
            f"  {name:<12}{len(entries):>7}{ours:>9.0f}{dispatched:>12.0f}"
            f"{theirs:>9.0f}{ratio:>7.2f}x  {right}/{len(entries)}"
        )
    return 1 if slower else 0


SAMPLED = ("sync", "tile", "merge", "mirror", "multiply", "scale", "transparent")
"""Every command the cartridge sends, including the one that computes nothing.

Sync computes nothing and so looks like a command not worth pricing, which is
how it was left out at first. It is the third most frequent thing the cartridge
sends, 180,975 times across the three tours against 3,155,798 of everything
else, and the replacement still walks the whole dispatch path to answer it. A
report that omits it cannot be summed into a per frame figure, which is the one
question the report exists to answer.
"""


def sweep(
    rom: bytes,
    names: dict[str, int],
    trace: Any,
    wanted: int,
    wanted_commands: tuple[str, ...],
    dispatched: bool,
) -> dict[str, list[tuple[int, int, bool]]]:
    """One ordered pass over the sample, through one of the two entry paths.

    A pass gets a machine of its own and replays the sample from the start,
    rather than measuring each exchange twice on one machine. Two of the
    operations answer differently depending on what came before, and one of them
    is cheaper the second time: setting the transparent colour rebuilds a pair of
    tables only when the colour changed, so a repeat measures the early exit and
    reports the dispatched path as 212 cycles faster than the direct one.
    """
    import dsptrace

    seen: defaultdict[str, int] = defaultdict(int)
    rows: defaultdict[str, list[tuple[int, int, bool]]] = defaultdict(list)
    cpu, memory = machine(rom)
    enter(cpu, names["dsp_init"])
    for tx in dsptrace.transactions(dsptrace.records(trace)):
        if not tx.complete:
            continue
        if seen[tx.name] >= wanted:
            if all(seen[one] >= wanted for one in wanted_commands):
                break
            continue
        seen[tx.name] += 1

        exchange = (tx.command, tuple(tx.lengths), bytes(tx.parameters), len(tx.output))
        spent = measure(cpu, memory, names, *exchange, dispatched=dispatched)
        got = produced(memory, len(tx.output))

        rows[tx.name].append(
            (spent, retail_cost(tx.name, tx.parameters, tx.output), got == bytes(tx.output))
        )
    return rows


def joined(
    direct: dict[str, list[tuple[int, int, bool]]],
    dispatched: dict[str, list[tuple[int, int, bool]]],
) -> dict[str, list[tuple[int, int, int, bool]]]:
    """The two passes side by side, one row per exchange."""
    return {
        name: [
            (one[0], two[0], one[1], one[2] and two[2])
            for one, two in zip(entries, dispatched.get(name, []), strict=True)
        ]
        for name, entries in direct.items()
    }


def main(argv: list[str], say: Any = print, wanted_commands: tuple[str, ...] = SAMPLED) -> int:
    """Measure every command against a sample of the cartridge's own traffic.

    Sampling stops once every command named has been seen the requested number
    of times, because a trace holds millions of exchanges and the cost of one
    command does not change with how many of them are measured.

    Each pass runs the whole sample in the order the cartridge issued it, because
    two of the commands answer differently depending on what came before: a merge
    reads the transparent colour a previous command set, so starting each
    exchange from a fresh chip would measure it against a colour the cartridge
    never chose.
    """
    rom_path = ROOT / "asm" / "dm-sym.sfc" if len(argv) < 2 else Path(argv[1])
    sym_path = rom_path.with_suffix(".sym") if len(argv) < 3 else Path(argv[2])
    trace = ROOT / "build" / "trace-s1.bin" if len(argv) < 4 else Path(argv[3])
    wanted = 60 if len(argv) < 5 else int(argv[4])

    if not rom_path.exists() or not sym_path.exists():
        say(f"  build {rom_path.name} and its symbols first")
        return 2

    if stale(sym_path, rom_path):
        say(f"  {sym_path.name} is older than {rom_path.name}; assemble them together")
        return 2

    rom = rom_path.read_bytes()
    names = symbols(sym_path.read_text())

    return report(
        joined(
            sweep(rom, names, trace, wanted, wanted_commands, dispatched=False),
            sweep(rom, names, trace, wanted, wanted_commands, dispatched=True),
        ),
        say,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
