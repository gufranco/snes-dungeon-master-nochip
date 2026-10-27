import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import dsptrace  # noqa: E402
import hardware  # noqa: E402

mos65xx = hardware.load("mos65xx")
snesdsp = hardware.load("snesdsp")

MODEL = "65816"

PART = "dsp2"

PREAMBLE = {dsptrace.COMMAND_TILE: 1}

TRAILING = {dsptrace.COMMAND_SYNC: 1}

Expected = Callable[[list[Any], list[int]], dict[int, bytes]]

BANK = 0x8000
WRAM = 0x20000

O_BUFFER = 0x000C00

LONG_ACCESS_CYCLES = 5

MOVE_CYCLES_PER_BYTE = 7

RETURN = 0x00FFFF

COLOUR_COMMAND = "transparent"

DECLARED_LENGTHS = {
    "sync": 0,
    "tile": 0,
    "transparent": 0,
    "multiply": 0,
    "merge": 1,
    "mirror": 1,
    "scale": 2,
}


class Ran(Exception):
    pass


class LoRom:
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
    stores = 1 + DECLARED_LENGTHS.get(command, 0)
    return stores * LONG_ACCESS_CYCLES + (len(parameters) + len(output)) * MOVE_CYCLES_PER_BYTE


def stale(symbols_path: Path, rom_path: Path) -> bool:
    return symbols_path.stat().st_mtime < rom_path.stat().st_mtime


def machine(rom: bytes) -> tuple[Any, LoRom]:
    memory = LoRom(rom)
    cpu = mos65xx.Cpu(MODEL, memory)
    cpu.reset()
    cpu.set_emulation(False)
    return cpu, memory


def enter(cpu: Any, address: int, limit: int = 4_000_000) -> int:
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

DESTINATION = 0x7E5000


TRAMPOLINE = 0x0084

DISPATCHED = "tramp_0084"

DESTINATION_OPERAND = TRAMPOLINE + 1
SOURCE_OPERAND = TRAMPOLINE + 2

PORT_BANK = 0x3F
WORK_RAM_BANK = 0x7E


def through(names: dict[str, int], dispatched: bool) -> tuple[int, int]:
    if dispatched:
        return names[DISPATCHED], names[DISPATCHED]
    return names["dsp_feed_wram"], names["dsp_drain_wram"]


def point(memory: LoRom, destination: int, source: int) -> None:
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
    at = DESTINATION & 0xFFFF
    return bytes(memory.wram[at : at + length])


def report(rows: dict[str, list[tuple[int, int, int, bool]]], say: Any = print) -> int:
    say(
        f"  {'command':<12}{'calls':>7}{'direct':>9}{'dispatched':>12}"
        f"{'retail':>9}{'ratio':>8}  correct"
    )
    wrong = 0
    for name in sorted(rows):
        entries = rows[name]
        ours = sum(one for one, _, _, _ in entries) / len(entries)
        dispatched = sum(two for _, two, _, _ in entries) / len(entries)
        theirs = sum(three for _, _, three, _ in entries) / len(entries)
        right = sum(1 for _, _, _, ok in entries if ok)
        wrong += len(entries) - right
        ratio = ours / theirs if theirs else 0.0
        say(
            f"  {name:<12}{len(entries):>7}{ours:>9.0f}{dispatched:>12.0f}"
            f"{theirs:>9.0f}{ratio:>7.2f}x  {right}/{len(entries)}"
        )
    if wrong:
        say(f"  {wrong} answers did not match what the cartridge's chip returned")
        return 1
    return 0


SETTLED_FRAME = 600

SCAN_LIMIT = 200_000

SAMPLED = ("sync", "tile", "merge", "mirror", "multiply", "scale", "transparent")


def collect(trace: Any, after: int = SETTLED_FRAME, limit: int = SCAN_LIMIT) -> list[Any]:
    import dsptrace

    found: list[Any] = []
    for tx in dsptrace.transactions(dsptrace.records(trace)):
        if not tx.complete or tx.frame < after:
            continue
        found.append(
            (tx.name, tx.command, tuple(tx.lengths), bytes(tx.parameters), bytes(tx.output))
        )
        if len(found) >= limit:
            break
    return found


def chosen(found: Any, wanted: int, colour: str = COLOUR_COMMAND) -> tuple[list[int], list[int]]:
    places: defaultdict[str, list[int]] = defaultdict(list)
    for index, one in enumerate(found):
        places[one[0]].append(index)

    replay: set[int] = set()
    record: set[int] = set()
    for name, at in places.items():
        if name == colour:
            replay.update(at)
        stride = max(1, len(at) // wanted)
        taken = at[::stride][:wanted]
        record.update(taken)
        replay.update(taken)
    return sorted(replay), sorted(record)


def chip(build: Callable[[str], Any] | None = None) -> Any:
    return (build or snesdsp.Chip)(PART)


def why_not() -> Any:
    return snesdsp.why_not()


def recorded(found: list[Any], replay: list[int]) -> dict[int, bytes]:
    return {index: found[index][4] for index in replay}


def exchange(part: Any, one: Any) -> bytes:
    _, command, lengths, parameters, output = one
    for byte in (command, *lengths, *parameters):
        part.write(byte)
    for _ in range(PREAMBLE.get(command, 0)):
        hardware.answer(part)
    answer = bytes(hardware.answer(part) for _ in range(len(output)))
    for _ in range(TRAILING.get(command, 0)):
        hardware.answer(part)
    return answer


def answered(part: Any, found: list[Any], replay: list[int]) -> dict[int, bytes]:
    return {index: exchange(part, found[index]) for index in replay}


def sweep(
    rom: bytes,
    names: dict[str, int],
    trace: Any,
    wanted: int,
    wanted_commands: tuple[str, ...],
    dispatched: bool,
    after: int = SETTLED_FRAME,
    expected: Expected = recorded,
) -> dict[str, list[tuple[int, int, bool]]]:
    found = collect(trace, after)
    replay, record = chosen(found, wanted)
    keep = set(record)
    answers = expected(found, replay)

    rows: defaultdict[str, list[tuple[int, int, bool]]] = defaultdict(list)
    cpu, memory = machine(rom)
    enter(cpu, names["dsp_init"])
    for index in replay:
        name, command, lengths, parameters, output = found[index]
        spent = measure(cpu, memory, names, command, lengths, parameters, len(output), dispatched)
        if index not in keep:
            continue
        got = produced(memory, len(output))
        rows[name].append((spent, retail_cost(name, parameters, output), got == answers[index]))
    return rows


def joined(
    direct: dict[str, list[tuple[int, int, bool]]],
    dispatched: dict[str, list[tuple[int, int, bool]]],
) -> dict[str, list[tuple[int, int, int, bool]]]:
    return {
        name: [
            (one[0], two[0], one[1], one[2] and two[2])
            for one, two in zip(entries, dispatched.get(name, []), strict=True)
        ]
        for name, entries in direct.items()
    }


def main(
    argv: list[str],
    say: Any = print,
    wanted_commands: tuple[str, ...] = SAMPLED,
    build: Callable[[str], Any] | None = None,
    refuses: Callable[[], Any] = why_not,
) -> int:
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

    reason = refuses()
    if reason:
        say(f"  nothing to hold the answers to: {reason}")
        return 2

    rom = rom_path.read_bytes()
    names = symbols(sym_path.read_text())

    def against_the_part(found: list[Any], replay: list[int]) -> dict[int, bytes]:
        return answered(chip(build), found, replay)

    return report(
        joined(
            sweep(rom, names, trace, wanted, wanted_commands, False, expected=against_the_part),
            sweep(rom, names, trace, wanted, wanted_commands, True, expected=against_the_part),
        ),
        say,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    raise SystemExit(main(sys.argv))
