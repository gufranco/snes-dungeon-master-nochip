import random
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

CASES_ASM = BUILD / "cpu-cases.asm"
CASES_ROM = BUILD / "cpu-cases.sfc"
CASES_DUMP = BUILD / "cpu-cases-wram.bin"

ASAR_IMAGE = "dungeon-master-nochip/asar:1.81"
EMU_IMAGE = "dungeon-master-nochip/emu:dev"

RESULT_BASE = 0x7F0000
RESULT_STRIDE = 16
SCRATCH_BASE = 0x7E2000
SCRATCH_BYTES = 0x100
DONE_FLAG = 0x7F8000
PROGRESS = 0x7F8004
CASE_PC = 0x7E8000
DIRECT_PAGE = 0x0400
STACK_TOP = 0x1F00
STACK_WINDOW = (0x1EF0, 0x1F10)
POINTER_WINDOW = (0x0400, 0x0540)
POINTER_MASK = 0x3F

MODEL = "65816"
"""The part this cartridge runs, named because the family covers sixteen of them."""

ROM_BYTES = 0x80000
CASES_PER_BANK = 180
FIRST_CASE_BANK = 0x01
FRAMES_BASE = 120
FRAMES_PER_CASE = 1
EXAMPLE_LIMIT = 12


sys.path.insert(0, str(ROOT))
import hardware  # noqa: E402

hardware.install()

import mos65xx as emu65816  # noqa: E402
from mos65xx import opcodes65816 as wdc65816  # noqa: E402
from mos65xx.wdc65816 import IMMEDIATE_MODES, INDEX_WIDTH_OPS  # noqa: E402, F401


class LoRomMemory:
    def __init__(self, rom: Any) -> None:
        self.rom = rom
        self.wram = bytearray(0x20000)

    def _wram_offset(self, address: int) -> int | None:
        bank = (address >> 16) & 0xFF
        offset = address & 0xFFFF
        if bank == 0x7E:
            return offset
        if bank == 0x7F:
            return 0x10000 + offset
        if (bank < 0x40 or 0x80 <= bank < 0xC0) and offset < 0x2000:
            return offset
        return None

    def _rom_offset(self, address: int) -> int | None:
        bank = (address >> 16) & 0xFF
        offset = address & 0xFFFF
        if bank in (0x7E, 0x7F) or offset < 0x8000:
            return None
        linear = (bank & 0x7F) * 0x8000 + (offset - 0x8000)
        return linear % len(self.rom)

    def read8(self, address: int) -> int:
        at = self._wram_offset(address)
        if at is not None:
            return self.wram[at]
        at = self._rom_offset(address)
        return self.rom[at] if at is not None else 0x00

    def write8(self, address: Any, value: Any) -> None:
        at = self._wram_offset(address)
        if at is not None:
            self.wram[at] = value & 0xFF


SKIP_MNEMONICS = frozenset(
    {
        "brk",
        "cop",
        "rti",
        "stp",
        "wai",
        "jmp",
        "jml",
        "jsr",
        "jsl",
        "rts",
        "rtl",
        "bra",
        "brl",
        "beq",
        "bne",
        "bcs",
        "bcc",
        "bmi",
        "bpl",
        "bvs",
        "bvc",
        "mvn",
        "mvp",
        "per",
        "txs",
        "tas",
        "wdm",
        "xce",
    }
)

SKIP_MODES = frozenset(
    {
        "indirectPC",
        "indirectLongPC",
        "indirectX",
        "absolutePC",
        "move",
        "absoluteLong",
        "absoluteLongX",
        "indirectLong",
        "indirectLongY",
        "stackIndirect",
    }
)


def testable_opcodes() -> list[tuple[int, Any, Any]]:
    return [
        (opcode, mnemonic, mode)
        for opcode, (mnemonic, mode) in enumerate(wdc65816.OPCODES)
        if mnemonic not in SKIP_MNEMONICS and mode not in SKIP_MODES
    ]


def operand_size(mode: Any, wide: bool) -> int:
    if mode in ("immediateA", "immediateX"):
        return 2 if wide else 1
    size: int = wdc65816.MODE_SIZE[mode]
    return size


def build_cases(seed: int, count: int) -> list[Any]:
    rng = random.Random(seed)
    catalogue = testable_opcodes()
    cases: list[Any] = []
    for index in range(count):
        opcode, mnemonic, mode = catalogue[index % len(catalogue)]
        status = rng.randrange(0x00, 0x100) | emu65816.FLAG_I
        status &= ~emu65816.FLAG_D
        wide = (
            not (status & emu65816.FLAG_X)
            if mnemonic in INDEX_WIDTH_OPS
            else not (status & emu65816.FLAG_M)
        )
        size = operand_size(mode, wide)
        operand = bytes(rng.randrange(0x00, 0x40) for _ in range(size))
        cases.append(
            {
                "opcode": opcode,
                "mnemonic": mnemonic,
                "mode": mode,
                "bytes": bytes([opcode]) + operand,
                "a": rng.randrange(0x0000, 0x10000),
                "x": rng.randrange(0x0000, 0x0100),
                "y": rng.randrange(0x0000, 0x0100),
                "p": status,
                "d": DIRECT_PAGE,
                "db": 0x7E,
            }
        )
    return cases


def emit_asm(cases: Any) -> str:
    lines = [
        "lorom",
        "",
        "org $008000",
        "reset:",
        "    sei",
        "    clc",
        "    xce",
        "    rep #$38",
        f"    ldx #${STACK_TOP:04X}",
        "    txs",
        "    lda #$0000",
        "    tcd",
        "    sep #$20",
        "    lda #$8F",
        "    sta $2100",
        "    rep #$30",
        "",
        "    ldx #$0000",
        "fill_work_ram:",
        "    txa",
        "    sep #$20",
        "    sta.l $7E0000,x",
        "    sta.l $7F0000,x",
        "    rep #$30",
        "    inx",
        "    bne fill_work_ram",
        "    jml case_0",
        "",
    ]

    for index, case in enumerate(cases):
        result = RESULT_BASE + index * RESULT_STRIDE
        if index % CASES_PER_BANK == 0:
            bank = FIRST_CASE_BANK + index // CASES_PER_BANK
            lines += [f"org ${bank:02X}8000", ""]
        lines += [
            f"case_{index}:",
            "    rep #$30",
            f"    lda #${index:04X}",
            f"    sta.l ${PROGRESS:06X}",
            f"    ldx #${STACK_TOP:04X}",
            "    txs",
            f"    ldx #${STACK_WINDOW[0]:04X}",
            f"restore_{index}:",
            "    txa",
            "    sep #$20",
            "    sta.l $7E0000,x",
            "    rep #$30",
            "    inx",
            f"    cpx #${STACK_WINDOW[1]:04X}",
            f"    bne restore_{index}",
            f"    ldx #${POINTER_WINDOW[0]:04X}",
            f"pointers_{index}:",
            "    txa",
            f"    and #${POINTER_MASK:04X}",
            "    sep #$20",
            "    sta.l $7E0000,x",
            "    rep #$30",
            "    inx",
            f"    cpx #${POINTER_WINDOW[1]:04X}",
            f"    bne pointers_{index}",
            "    sep #$20",
            f"    lda #${case['p']:02X}",
            "    pha",
            "    rep #$30",
            f"    lda #${case['d']:04X}",
            "    tcd",
            f"    pea ${case['db']:02X}{case['db']:02X}",
            "    plb",
            "    plb",
            f"    ldx #${case['x']:04X}",
            f"    ldy #${case['y']:04X}",
            f"    lda #${case['a']:04X}",
            "    plp",
            "    db " + ",".join(f"${b:02X}" for b in case["bytes"]),
            "    php",
            "    rep #$30",
            "    pha",
            "    phx",
            "    phy",
            "    pla",
            f"    sta.l ${result + 4:06X}",
            "    pla",
            f"    sta.l ${result + 2:06X}",
            "    pla",
            f"    sta.l ${result + 0:06X}",
            "    sep #$20",
            "    pla",
            f"    sta.l ${result + 6:06X}",
            "    rep #$30",
            "    tsc",
            f"    sta.l ${result + 8:06X}",
            "    tdc",
            f"    sta.l ${result + 10:06X}",
            "    sep #$20",
            "    phb",
            "    pla",
            f"    sta.l ${result + 12:06X}",
            "    rep #$30",
            "    lda #$0000",
            "    tcd",
        ]
        if (index + 1) % CASES_PER_BANK == 0 and index + 1 < len(cases):
            lines.append(f"    jml case_{index + 1}")
        lines.append("")

    lines += [
        "    sep #$20",
        "    lda #$A5",
        f"    sta.l ${DONE_FLAG:06X}",
        "    rep #$20",
        "halt:",
        "    bra halt",
        "",
        "org $00FFC0",
        '    db "CPU DIFFERENTIAL TEST"',
        "    db $20",
        "    db $00",
        "    db $0A",
        "    db $00",
        "    db $01",
        "    db $00",
        "    db $00",
        "    dw $0000",
        "    dw $0000",
        "org $00FFFC",
        "    dw reset",
        "    dw $0000",
    ]
    return "\n".join(lines) + "\n"


def assemble_command() -> list[str]:
    """What assembling the case cartridge shells out to."""
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--volume",
        f"{BUILD}:/work",
        ASAR_IMAGE,
        "--no-title-check",
        CASES_ASM.name,
        CASES_ROM.name,
    ]


def _shell_out(args: list[str]) -> Any:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def assemble(
    text: str,
    execute: Any = _shell_out,
    say: Callable[[str], None] = print,
    complain: Callable[[str], None] | None = None,
) -> Any:
    """The case cartridge, assembled by the pinned toolchain."""
    complain = say if complain is None else complain
    BUILD.mkdir(exist_ok=True)
    CASES_ASM.write_text(text)
    CASES_ROM.write_bytes(bytes(ROM_BYTES))
    result = execute(assemble_command())
    if result.returncode != 0:
        say(result.stdout)
        complain(result.stderr)
        return False
    return True


def frames_for(count: int) -> int:
    return FRAMES_BASE + count * FRAMES_PER_CASE


def emulator_command(frames: int) -> list[str]:
    """What running the case cartridge shells out to."""
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--env",
        f"DMDUMP={CASES_DUMP.name}",
        "--volume",
        f"{BUILD}:/work",
        EMU_IMAGE,
        CASES_ROM.name,
        str(frames),
    ]


def run_in_snes9x(
    frames: int,
    execute: Any = _shell_out,
    say: Callable[[str], None] = print,
    complain: Callable[[str], None] | None = None,
) -> bytes | None:
    """The cases walked by the emulator, and the memory it left behind."""
    complain = say if complain is None else complain
    result = execute(emulator_command(frames))
    if result.returncode != 0:
        say(result.stdout)
        complain(result.stderr)
        return None
    return CASES_DUMP.read_bytes()


def run_in_python(cases: Any, rom: bytes) -> list[Any]:
    memory = LoRomMemory(rom)
    for index in range(0x10000):
        memory.wram[index] = index & 0xFF
        memory.wram[0x10000 + index] = index & 0xFF

    found: list[Any] = []
    for case in cases:
        cpu = emu65816.Cpu(MODEL, memory)
        cpu.d = case["d"]
        cpu.db = case["db"]
        cpu.x = case["x"]
        cpu.y = case["y"]
        cpu.a = case["a"]
        for address in range(*STACK_WINDOW):
            memory.wram[address] = address & 0xFF
        for address in range(*POINTER_WINDOW):
            memory.wram[address] = address & POINTER_MASK
        memory.wram[STACK_TOP] = case["p"]
        memory.wram[STACK_TOP - 1] = case["db"]
        memory.wram[STACK_TOP - 2] = case["db"]
        cpu.s = STACK_TOP
        cpu.set_status(case["p"])
        cpu.pb = (CASE_PC >> 16) & 0xFF
        cpu.pc = CASE_PC & 0xFFFF
        for offset, value in enumerate(case["bytes"]):
            memory.write8(CASE_PC + offset, value)
        cpu.step()
        found.append(
            {
                "a": cpu.a & 0xFFFF,
                "x": cpu.x & 0xFFFF,
                "y": cpu.y & 0xFFFF,
                "p": cpu.status(),
                "d": cpu.d & 0xFFFF,
                "db": cpu.db & 0xFF,
            }
        )
    return found


def read_results(dump: bytes, count: int) -> list[Any]:
    found: list[Any] = []
    for index in range(count):
        at = 0x10000 + (RESULT_BASE & 0xFFFF) + index * RESULT_STRIDE
        found.append(
            {
                "a": dump[at] | (dump[at + 1] << 8),
                "x": dump[at + 2] | (dump[at + 3] << 8),
                "y": dump[at + 4] | (dump[at + 5] << 8),
                "p": dump[at + 6],
                "d": dump[at + 10] | (dump[at + 11] << 8),
                "db": dump[at + 12],
            }
        )
    return found


def compare(cases: Any, wanted: Any, found: Any) -> list[Any]:
    mismatches: list[Any] = []
    for case, want, got in zip(cases, wanted, found, strict=True):
        differences = [field for field in ("a", "x", "y", "p") if want[field] != got[field]]
        if differences:
            mismatches.append((case, want, got, differences))
    return mismatches


def lines_for(cases: Any, mismatches: Any) -> list[str]:
    """What disagreed, named by opcode so it can be looked up."""
    lines: list[Any] = []
    for case, want, got, fields in mismatches[:EXAMPLE_LIMIT]:
        detail = ", ".join(
            f"{one} snes9x {want[one]:#06x} python {got[one]:#06x}" for one in fields
        )
        lines.append(
            f"    ${case['opcode']:02X} {case['mnemonic']:<4s} {case['mode']:<18s} {detail}"
        )
    lines.append(f"  {len(cases) - len(mismatches)} of {len(cases)} agree with snes9x")
    return lines


def main(
    argv: list[str],
    build: Any = None,
    walk: Any = None,
    say: Callable[[str], None] = print,
    complain: Callable[[str], None] | None = None,
) -> int:
    """Cases run on both, with the two that shell out passed in so a run can be checked."""
    complain = say if complain is None else complain
    build = assemble if build is None else build
    walk = run_in_snes9x if walk is None else walk

    seed = int(argv[1]) if len(argv) > 1 else 0
    count = int(argv[2]) if len(argv) > 2 else 400

    cases = build_cases(seed, count)
    say(f"  {len(cases)} cases from seed {seed}")

    if not build(emit_asm(cases)):
        return 1

    rom = CASES_ROM.read_bytes()
    dump = walk(frames_for(len(cases)))
    if dump is None:
        return 1
    if dump[0x10000 + (DONE_FLAG & 0xFFFF)] != 0xA5:
        complain("  the cartridge did not finish its cases")
        return 1

    mismatches = compare(cases, read_results(dump, len(cases)), run_in_python(cases, rom))
    for line in lines_for(cases, mismatches):
        say(line)
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
