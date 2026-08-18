import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEP_LIMIT = 2_000_000


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wdc65816 = _load("wdc65816")

OPCODES = wdc65816.OPCODES

FLAG_C = 0x01
FLAG_Z = 0x02
FLAG_I = 0x04
FLAG_D = 0x08
FLAG_X = 0x10
FLAG_M = 0x20
FLAG_V = 0x40
FLAG_N = 0x80

IMMEDIATE_MODES = frozenset({"immediate", "immediateA", "immediateX"})
INDEX_WIDTH_OPS = frozenset({"ldx", "ldy", "stx", "sty", "cpx", "cpy"})

BREAK_VECTOR = 0x00FFE6
COP_VECTOR = 0x00FFE4


class StepLimit(Exception):
    pass


class Unsupported(Exception):
    pass


class Stopped(Exception):
    pass


class Memory:
    def __init__(self, size=0x1000000):
        self.data = bytearray(size)

    def read8(self, address):
        return self.data[address & 0xFFFFFF]

    def write8(self, address, value):
        self.data[address & 0xFFFFFF] = value & 0xFF


class Cpu:
    def __init__(self, memory, step_limit=STEP_LIMIT):
        self.memory = memory
        self.step_limit = step_limit
        self.a = 0x0000
        self.x = 0x0000
        self.y = 0x0000
        self.s = 0x01FF
        self.d = 0x0000
        self.db = 0x00
        self.pb = 0x00
        self.pc = 0x0000
        self.n = False
        self.v = False
        self.m8 = True
        self.x8 = True
        self.decimal = False
        self.irq_disable = True
        self.z = False
        self.c = False
        self.emulation = False
        self.steps = 0
        self.stopped = False
        self.waiting = False

    def status(self):
        value = 0
        value |= FLAG_N if self.n else 0
        value |= FLAG_V if self.v else 0
        value |= FLAG_M if self.m8 else 0
        value |= FLAG_X if self.x8 else 0
        value |= FLAG_D if self.decimal else 0
        value |= FLAG_I if self.irq_disable else 0
        value |= FLAG_Z if self.z else 0
        value |= FLAG_C if self.c else 0
        return value

    def set_status(self, value):
        self.n = bool(value & FLAG_N)
        self.v = bool(value & FLAG_V)
        self.decimal = bool(value & FLAG_D)
        self.irq_disable = bool(value & FLAG_I)
        self.z = bool(value & FLAG_Z)
        self.c = bool(value & FLAG_C)
        if self.emulation:
            self.m8 = True
            self.x8 = True
        else:
            self.m8 = bool(value & FLAG_M)
            self.x8 = bool(value & FLAG_X)
        if self.x8:
            self.x &= 0xFF
            self.y &= 0xFF

    def set_emulation(self, value):
        self.emulation = bool(value)
        if self.emulation:
            self.m8 = True
            self.x8 = True
            self.x &= 0xFF
            self.y &= 0xFF
            self.s = 0x0100 | (self.s & 0xFF)

    def read8(self, address):
        return self.memory.read8(address & 0xFFFFFF) & 0xFF

    def write8(self, address, value):
        self.memory.write8(address & 0xFFFFFF, value & 0xFF)

    def read16(self, address):
        return self.read8(address) | (self.read8(address + 1) << 8)

    def read24(self, address):
        return self.read16(address) | (self.read8(address + 2) << 16)

    def read_value(self, address, wide):
        return self.read16(address) if wide else self.read8(address)

    def write_value(self, address, value, wide):
        self.write8(address, value)
        if wide:
            self.write8(address + 1, value >> 8)

    def fetch8(self):
        value = self.read8((self.pb << 16) | self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def fetch16(self):
        return self.fetch8() | (self.fetch8() << 8)

    def fetch24(self):
        return self.fetch16() | (self.fetch8() << 16)

    def push8(self, value):
        self.write8(self.s, value)
        if self.emulation:
            self.s = 0x0100 | ((self.s - 1) & 0xFF)
        else:
            self.s = (self.s - 1) & 0xFFFF

    def pull8(self):
        if self.emulation:
            self.s = 0x0100 | ((self.s + 1) & 0xFF)
        else:
            self.s = (self.s + 1) & 0xFFFF
        return self.read8(self.s)

    def push16(self, value):
        self.push8((value >> 8) & 0xFF)
        self.push8(value & 0xFF)

    def pull16(self):
        return self.pull8() | (self.pull8() << 8)

    def acc(self):
        return self.a & 0xFF if self.m8 else self.a & 0xFFFF

    def set_acc(self, value):
        if self.m8:
            self.a = (self.a & 0xFF00) | (value & 0xFF)
        else:
            self.a = value & 0xFFFF

    def set_nz(self, value, wide):
        mask = 0xFFFF if wide else 0xFF
        self.z = (value & mask) == 0
        self.n = bool(value & (0x8000 if wide else 0x80))

    def wide_for(self, mnemonic):
        if mnemonic in INDEX_WIDTH_OPS:
            return not self.x8
        return not self.m8

    def effective(self, mode, mnemonic):
        if mode == "direct":
            return (self.d + self.fetch8()) & 0xFFFF
        if mode == "directX":
            return (self.d + self.fetch8() + self.x) & 0xFFFF
        if mode == "directY":
            return (self.d + self.fetch8() + self.y) & 0xFFFF
        if mode == "absolute":
            return (self.db << 16) | self.fetch16()
        if mode == "absoluteX":
            return ((self.db << 16) | self.fetch16()) + self.x
        if mode == "absoluteY":
            return ((self.db << 16) | self.fetch16()) + self.y
        if mode == "absoluteLong":
            return self.fetch24()
        if mode == "absoluteLongX":
            return self.fetch24() + self.x
        if mode == "indirect":
            return (self.db << 16) | self.read16((self.d + self.fetch8()) & 0xFFFF)
        if mode == "indexedIndirectX":
            pointer = (self.d + self.fetch8() + self.x) & 0xFFFF
            return (self.db << 16) | self.read16(pointer)
        if mode == "indirectIndexedY":
            pointer = (self.d + self.fetch8()) & 0xFFFF
            return ((self.db << 16) | self.read16(pointer)) + self.y
        if mode == "indirectLong":
            return self.read24((self.d + self.fetch8()) & 0xFFFF)
        if mode == "indirectLongY":
            return self.read24((self.d + self.fetch8()) & 0xFFFF) + self.y
        if mode == "stack":
            return (self.s + self.fetch8()) & 0xFFFF
        if mode == "stackIndirect":
            pointer = (self.s + self.fetch8()) & 0xFFFF
            return ((self.db << 16) | self.read16(pointer)) + self.y
        raise Unsupported(f"{mnemonic} cannot use {mode}")

    def operand(self, mode, mnemonic):
        wide = self.wide_for(mnemonic)
        if mode in IMMEDIATE_MODES:
            if mode == "immediate":
                return self.fetch8()
            return self.fetch16() if wide else self.fetch8()
        return self.read_value(self.effective(mode, mnemonic), wide)

    def add_with_carry(self, value):
        wide = not self.m8
        bits = 16 if wide else 8
        left = self.acc()
        carry = 1 if self.c else 0

        if self.decimal:
            total = 0
            carry_in = carry
            for shift in range(0, bits, 4):
                digit = ((left >> shift) & 0xF) + ((value >> shift) & 0xF) + carry_in
                carry_in = 0
                if digit > 9:
                    digit += 6
                if digit > 0xF:
                    carry_in = 1
                    digit &= 0xF
                total |= digit << shift
            result = total
            self.c = bool(carry_in)
        else:
            result = left + value + carry
            self.c = result > (0xFFFF if wide else 0xFF)

        sign = 0x8000 if wide else 0x80
        self.v = bool(~(left ^ value) & (left ^ result) & sign)
        result &= 0xFFFF if wide else 0xFF
        self.set_nz(result, wide)
        self.set_acc(result)

    def subtract_with_carry(self, value):
        wide = not self.m8
        bits = 16 if wide else 8
        mask = 0xFFFF if wide else 0xFF
        left = self.acc()
        borrow = 0 if self.c else 1
        plain = left - value - borrow

        if self.decimal:
            total = 0
            borrow_in = borrow
            for shift in range(0, bits, 4):
                digit = ((left >> shift) & 0xF) - ((value >> shift) & 0xF) - borrow_in
                borrow_in = 0
                if digit < 0:
                    digit -= 6
                    borrow_in = 1
                total |= (digit & 0xF) << shift
            result = total & mask
            self.c = not borrow_in
        else:
            result = plain & mask
            self.c = plain >= 0

        sign = 0x8000 if wide else 0x80
        self.v = bool((left ^ value) & (left ^ (plain & mask)) & sign)
        self.set_nz(result, wide)
        self.set_acc(result)

    def compare(self, register, value, wide):
        mask = 0xFFFF if wide else 0xFF
        self.c = register >= value
        self.set_nz((register - value) & mask, wide)

    def step(self):
        if self.stopped:
            raise Stopped("the processor has been stopped")
        self.steps += 1
        if self.steps > self.step_limit:
            raise StepLimit(f"stopped after {self.steps} steps at ${self.pb:02X}:{self.pc:04X}")
        opcode = self.fetch8()
        mnemonic, mode = OPCODES[opcode]
        handler = getattr(self, f"op_{mnemonic}", None)
        if handler is None:
            raise Unsupported(f"{mnemonic} is not implemented")
        handler(mode)

    def call(self, address):
        self.pb = (address >> 16) & 0xFF
        self.pc = address & 0xFFFF
        depth = 0
        while True:
            mnemonic = OPCODES[self.read8((self.pb << 16) | self.pc)][0]
            if mnemonic in ("rts", "rtl"):
                if depth == 0:
                    return self
                depth -= 1
            elif mnemonic in ("jsr", "jsl"):
                depth += 1
            self.step()

    def run_until(self, predicate):
        while not predicate(self):
            self.step()
        return self

    def op_lda(self, mode):
        value = self.operand(mode, "lda")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_ldx(self, mode):
        value = self.operand(mode, "ldx")
        self.x = value
        self.set_nz(value, not self.x8)

    def op_ldy(self, mode):
        value = self.operand(mode, "ldy")
        self.y = value
        self.set_nz(value, not self.x8)

    def op_sta(self, mode):
        self.write_value(self.effective(mode, "sta"), self.acc(), not self.m8)

    def op_stx(self, mode):
        self.write_value(self.effective(mode, "stx"), self.x, not self.x8)

    def op_sty(self, mode):
        self.write_value(self.effective(mode, "sty"), self.y, not self.x8)

    def op_stz(self, mode):
        self.write_value(self.effective(mode, "stz"), 0, not self.m8)

    def op_tax(self, mode):
        self.x = self.a & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_tay(self, mode):
        self.y = self.a & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.y, not self.x8)

    def op_txa(self, mode):
        self.set_acc(self.x)
        self.set_nz(self.acc(), not self.m8)

    def op_tya(self, mode):
        self.set_acc(self.y)
        self.set_nz(self.acc(), not self.m8)

    def op_txy(self, mode):
        self.y = self.x
        self.set_nz(self.y, not self.x8)

    def op_tyx(self, mode):
        self.x = self.y
        self.set_nz(self.x, not self.x8)

    def op_tsx(self, mode):
        self.x = self.s & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_txs(self, mode):
        self.s = 0x0100 | (self.x & 0xFF) if self.emulation else self.x & 0xFFFF

    def op_tas(self, mode):
        self.s = 0x0100 | (self.a & 0xFF) if self.emulation else self.a & 0xFFFF

    def op_tsa(self, mode):
        self.a = self.s & 0xFFFF
        self.set_nz(self.a, True)

    def op_tad(self, mode):
        self.d = self.a & 0xFFFF
        self.set_nz(self.d, True)

    def op_tda(self, mode):
        self.a = self.d & 0xFFFF
        self.set_nz(self.a, True)

    def op_xba(self, mode):
        self.a = ((self.a >> 8) | (self.a << 8)) & 0xFFFF
        self.set_nz(self.a & 0xFF, False)

    def op_xce(self, mode):
        carry = self.c
        self.c = self.emulation
        self.set_emulation(carry)

    def op_and(self, mode):
        value = self.acc() & self.operand(mode, "and")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_ora(self, mode):
        value = self.acc() | self.operand(mode, "ora")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_eor(self, mode):
        value = self.acc() ^ self.operand(mode, "eor")
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_adc(self, mode):
        self.add_with_carry(self.operand(mode, "adc"))

    def op_sbc(self, mode):
        self.subtract_with_carry(self.operand(mode, "sbc"))

    def op_cmp(self, mode):
        self.compare(self.acc(), self.operand(mode, "cmp"), not self.m8)

    def op_cpx(self, mode):
        self.compare(self.x, self.operand(mode, "cpx"), not self.x8)

    def op_cpy(self, mode):
        self.compare(self.y, self.operand(mode, "cpy"), not self.x8)

    def op_bit(self, mode):
        value = self.operand(mode, "bit")
        wide = not self.m8
        self.z = (self.acc() & value) == 0
        if mode not in IMMEDIATE_MODES:
            self.n = bool(value & (0x8000 if wide else 0x80))
            self.v = bool(value & (0x4000 if wide else 0x40))

    def _read_modify_write(self, mode, mnemonic, operation):
        wide = not self.m8
        if mode == "implied":
            self.set_acc(operation(self.acc(), wide))
            return
        address = self.effective(mode, mnemonic)
        self.write_value(address, operation(self.read_value(address, wide), wide), wide)

    def op_asl(self, mode):
        def shift(value, wide):
            self.c = bool(value & (0x8000 if wide else 0x80))
            result = (value << 1) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "asl", shift)

    def op_lsr(self, mode):
        def shift(value, wide):
            self.c = bool(value & 1)
            result = value >> 1
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "lsr", shift)

    def op_rol(self, mode):
        def rotate(value, wide):
            carry = 1 if self.c else 0
            self.c = bool(value & (0x8000 if wide else 0x80))
            result = ((value << 1) | carry) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "rol", rotate)

    def op_ror(self, mode):
        def rotate(value, wide):
            carry = (0x8000 if wide else 0x80) if self.c else 0
            self.c = bool(value & 1)
            result = (value >> 1) | carry
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "ror", rotate)

    def op_inc(self, mode):
        def bump(value, wide):
            result = (value + 1) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "inc", bump)

    def op_dec(self, mode):
        def drop(value, wide):
            result = (value - 1) & (0xFFFF if wide else 0xFF)
            self.set_nz(result, wide)
            return result

        self._read_modify_write(mode, "dec", drop)

    def op_trb(self, mode):
        wide = not self.m8
        address = self.effective(mode, "trb")
        value = self.read_value(address, wide)
        self.z = (value & self.acc()) == 0
        self.write_value(address, value & ~self.acc(), wide)

    def op_tsb(self, mode):
        wide = not self.m8
        address = self.effective(mode, "tsb")
        value = self.read_value(address, wide)
        self.z = (value & self.acc()) == 0
        self.write_value(address, value | self.acc(), wide)

    def op_inx(self, mode):
        self.x = (self.x + 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_iny(self, mode):
        self.y = (self.y + 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.y, not self.x8)

    def op_dex(self, mode):
        self.x = (self.x - 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.x, not self.x8)

    def op_dey(self, mode):
        self.y = (self.y - 1) & (0xFF if self.x8 else 0xFFFF)
        self.set_nz(self.y, not self.x8)

    def op_clc(self, mode):
        self.c = False

    def op_sec(self, mode):
        self.c = True

    def op_cld(self, mode):
        self.decimal = False

    def op_sed(self, mode):
        self.decimal = True

    def op_cli(self, mode):
        self.irq_disable = False

    def op_sei(self, mode):
        self.irq_disable = True

    def op_clv(self, mode):
        self.v = False

    def op_rep(self, mode):
        self.set_status(self.status() & ~self.fetch8())

    def op_sep(self, mode):
        self.set_status(self.status() | self.fetch8())

    def op_pha(self, mode):
        self.push8(self.a) if self.m8 else self.push16(self.a)

    def op_pla(self, mode):
        value = self.pull8() if self.m8 else self.pull16()
        self.set_acc(value)
        self.set_nz(value, not self.m8)

    def op_phx(self, mode):
        self.push8(self.x) if self.x8 else self.push16(self.x)

    def op_plx(self, mode):
        self.x = self.pull8() if self.x8 else self.pull16()
        self.set_nz(self.x, not self.x8)

    def op_phy(self, mode):
        self.push8(self.y) if self.x8 else self.push16(self.y)

    def op_ply(self, mode):
        self.y = self.pull8() if self.x8 else self.pull16()
        self.set_nz(self.y, not self.x8)

    def op_php(self, mode):
        self.push8(self.status())

    def op_plp(self, mode):
        self.set_status(self.pull8())

    def op_phb(self, mode):
        self.push8(self.db)

    def op_plb(self, mode):
        self.db = self.pull8()
        self.set_nz(self.db, False)

    def op_phd(self, mode):
        self.push16(self.d)

    def op_pld(self, mode):
        self.d = self.pull16()
        self.set_nz(self.d, True)

    def op_phk(self, mode):
        self.push8(self.pb)

    def op_pea(self, mode):
        self.push16(self.fetch16())

    def op_pei(self, mode):
        self.push16(self.read16((self.d + self.fetch8()) & 0xFFFF))

    def op_per(self, mode):
        offset = self.fetch16()
        self.push16((self.pc + self._signed16(offset)) & 0xFFFF)

    @staticmethod
    def _signed8(value):
        return value - 0x100 if value & 0x80 else value

    @staticmethod
    def _signed16(value):
        return value - 0x10000 if value & 0x8000 else value

    def _branch(self, taken):
        offset = self.fetch8()
        if taken:
            self.pc = (self.pc + self._signed8(offset)) & 0xFFFF

    def op_bra(self, mode):
        self._branch(True)

    def op_beq(self, mode):
        self._branch(self.z)

    def op_bne(self, mode):
        self._branch(not self.z)

    def op_bcs(self, mode):
        self._branch(self.c)

    def op_bcc(self, mode):
        self._branch(not self.c)

    def op_bmi(self, mode):
        self._branch(self.n)

    def op_bpl(self, mode):
        self._branch(not self.n)

    def op_bvs(self, mode):
        self._branch(self.v)

    def op_bvc(self, mode):
        self._branch(not self.v)

    def op_brl(self, mode):
        offset = self.fetch16()
        self.pc = (self.pc + self._signed16(offset)) & 0xFFFF

    def op_jmp(self, mode):
        if mode == "absolutePC":
            self.pc = self.fetch16()
            return
        if mode == "indirectPC":
            self.pc = self.read16(self.fetch16())
            return
        if mode == "indirectX":
            self.pc = self.read16((self.pb << 16) | ((self.fetch16() + self.x) & 0xFFFF))
            return
        raise Unsupported(f"jmp cannot use {mode}")

    def op_jml(self, mode):
        if mode == "absoluteLong":
            target = self.fetch24()
        elif mode == "indirectLongPC":
            target = self.read24(self.fetch16())
        else:
            raise Unsupported(f"jml cannot use {mode}")
        self.pb = (target >> 16) & 0xFF
        self.pc = target & 0xFFFF

    def op_jsr(self, mode):
        if mode == "absolutePC":
            target = self.fetch16()
        elif mode == "indirectX":
            target = self.read16((self.pb << 16) | ((self.fetch16() + self.x) & 0xFFFF))
        else:
            raise Unsupported(f"jsr cannot use {mode}")
        self.push16((self.pc - 1) & 0xFFFF)
        self.pc = target

    def op_jsl(self, mode):
        target = self.fetch24()
        self.push8(self.pb)
        self.push16((self.pc - 1) & 0xFFFF)
        self.pb = (target >> 16) & 0xFF
        self.pc = target & 0xFFFF

    def op_rts(self, mode):
        self.pc = (self.pull16() + 1) & 0xFFFF

    def op_rtl(self, mode):
        self.pc = (self.pull16() + 1) & 0xFFFF
        self.pb = self.pull8()

    def op_rti(self, mode):
        self.set_status(self.pull8())
        self.pc = self.pull16()
        if not self.emulation:
            self.pb = self.pull8()

    def _software_interrupt(self, vector):
        self.fetch8()
        if not self.emulation:
            self.push8(self.pb)
        self.push16(self.pc)
        self.push8(self.status())
        self.irq_disable = True
        self.decimal = False
        self.pb = 0x00
        self.pc = self.read16(vector)

    def op_brk(self, mode):
        self._software_interrupt(BREAK_VECTOR)

    def op_cop(self, mode):
        self._software_interrupt(COP_VECTOR)

    def _block_move(self, direction):
        destination = self.fetch8()
        source = self.fetch8()
        self.db = destination
        self.write8((destination << 16) | self.y, self.read8((source << 16) | self.x))
        mask = 0xFF if self.x8 else 0xFFFF
        self.x = (self.x + direction) & mask
        self.y = (self.y + direction) & mask
        self.a = (self.a - 1) & 0xFFFF
        if self.a != 0xFFFF:
            self.pc = (self.pc - 3) & 0xFFFF

    def op_mvn(self, mode):
        self._block_move(1)

    def op_mvp(self, mode):
        self._block_move(-1)

    def op_nop(self, mode):
        return

    def op_wdm(self, mode):
        self.fetch8()

    def op_stp(self, mode):
        self.stopped = True

    def op_wai(self, mode):
        self.waiting = True
