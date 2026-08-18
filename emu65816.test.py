import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "emu65816.py"


def load_module():
    spec = importlib.util.spec_from_file_location("emu65816", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


emu = load_module()

NATIVE_16 = 0x00
NATIVE_8 = emu.FLAG_M | emu.FLAG_X


class FlatMemory:
    def __init__(self, data=None):
        self.cells = dict(data or {})

    def read8(self, address):
        return self.cells.get(address & 0xFFFFFF, 0x00)

    def write8(self, address, value):
        self.cells[address & 0xFFFFFF] = value & 0xFF


def run(code, base=0x008000, memory=None, status=NATIVE_8, **registers):
    memory = memory or FlatMemory()
    for offset, byte in enumerate(code):
        memory.cells[base + offset] = byte
    cpu = emu.Cpu(memory)
    cpu.set_status(status)
    for name, value in registers.items():
        setattr(cpu, name, value)
    cpu.call(base)
    return cpu


RTL = 0x6B


class CoverageTest(unittest.TestCase):
    def test_every_opcode_has_a_handler(self):
        without = [
            opcode
            for opcode, (mnemonic, _) in enumerate(emu.OPCODES)
            if not hasattr(emu.Cpu, f"op_{mnemonic}")
        ]

        self.assertEqual(without, [])

    def test_the_table_covers_the_whole_byte(self):
        self.assertEqual(len(emu.OPCODES), 256)

    def test_the_reserved_opcode_is_a_two_byte_no_operation(self):
        memory = FlatMemory()

        cpu = run([0x42, 0xFF, RTL], memory=memory)

        self.assertEqual(cpu.pc, 0x8002)


class ResetStateTest(unittest.TestCase):
    def test_the_registers_start_eight_bits_wide(self):
        cpu = emu.Cpu(FlatMemory())

        self.assertTrue(cpu.m8)
        self.assertTrue(cpu.x8)


class WidthTest(unittest.TestCase):
    def test_rep_widens_the_accumulator(self):
        cpu = run([0xC2, 0x20, RTL])

        self.assertFalse(cpu.m8)

    def test_sep_narrows_the_accumulator(self):
        cpu = run([0xE2, 0x20, RTL], status=NATIVE_16)

        self.assertTrue(cpu.m8)

    def test_an_immediate_load_follows_the_declared_width(self):
        cpu = run([0xA9, 0x34, 0x12, RTL], status=NATIVE_16)

        self.assertEqual(cpu.a, 0x1234)

    def test_narrowing_the_index_truncates_it(self):
        cpu = run([0xE2, 0x10, RTL], status=NATIVE_16, x=0x1234)

        self.assertEqual(cpu.x, 0x34)

    def test_the_hidden_accumulator_half_survives_a_narrow_load(self):
        cpu = run([0xA9, 0x99, RTL], a=0x1234)

        self.assertEqual(cpu.a, 0x1299)


class AddressingTest(unittest.TestCase):
    def test_absolute_reads_through_the_data_bank(self):
        memory = FlatMemory({0x600005: 0x77})

        cpu = run([0xAD, 0x05, 0x00, RTL], memory=memory, db=0x60)

        self.assertEqual(cpu.a & 0xFF, 0x77)

    def test_absolute_indexed_by_y_reads_through_the_data_bank(self):
        memory = FlatMemory({0x600005: 0x77})

        cpu = run([0xB9, 0x00, 0x00, RTL], memory=memory, db=0x60, y=0x05)

        self.assertEqual(cpu.a & 0xFF, 0x77)

    def test_a_long_read_ignores_the_data_bank(self):
        memory = FlatMemory({0x610042: 0x99})

        cpu = run([0xAF, 0x42, 0x00, 0x61, RTL], memory=memory, db=0x00)

        self.assertEqual(cpu.a & 0xFF, 0x99)

    def test_direct_page_reads_are_offset_by_the_direct_register(self):
        memory = FlatMemory({0x000312: 0x5A})

        cpu = run([0xA5, 0x12, RTL], memory=memory, d=0x0300)

        self.assertEqual(cpu.a & 0xFF, 0x5A)

    def test_an_indirect_pointer_is_taken_from_the_direct_page(self):
        memory = FlatMemory({0x000310: 0x00, 0x000311: 0x20, 0x602000: 0x3C})

        cpu = run([0xB2, 0x10, RTL], memory=memory, d=0x0300, db=0x60)

        self.assertEqual(cpu.a & 0xFF, 0x3C)

    def test_a_long_indirect_pointer_carries_its_own_bank(self):
        memory = FlatMemory({0x000310: 0x00, 0x000311: 0x20, 0x000312: 0x7E, 0x7E2000: 0xC3})

        cpu = run([0xA7, 0x10, RTL], memory=memory, d=0x0300, db=0x00)

        self.assertEqual(cpu.a & 0xFF, 0xC3)

    def test_stack_relative_reads_sit_above_the_stack_pointer(self):
        memory = FlatMemory({0x0001F3: 0x6E})

        cpu = run([0xA3, 0x04, RTL], memory=memory, s=0x01EF)

        self.assertEqual(cpu.a & 0xFF, 0x6E)


class ArithmeticTest(unittest.TestCase):
    def test_addition_carries_out_of_eight_bits(self):
        cpu = run([0x18, 0x69, 0x01, RTL], a=0xFF)

        self.assertEqual(cpu.a & 0xFF, 0x00)
        self.assertTrue(cpu.c)

    def test_addition_sets_overflow_when_the_sign_is_wrong(self):
        cpu = run([0x18, 0x69, 0x01, RTL], a=0x7F)

        self.assertTrue(cpu.v)

    def test_addition_leaves_overflow_clear_when_the_sign_holds(self):
        cpu = run([0x18, 0x69, 0x01, RTL], a=0x00)

        self.assertFalse(cpu.v)

    def test_subtraction_borrows_when_the_carry_is_clear(self):
        cpu = run([0x18, 0xE9, 0x01, RTL], a=0x10)

        self.assertEqual(cpu.a & 0xFF, 0x0E)

    def test_subtraction_below_zero_clears_the_carry(self):
        cpu = run([0x38, 0xE9, 0x02, RTL], a=0x01)

        self.assertFalse(cpu.c)

    def test_decimal_addition_carries_at_nine(self):
        cpu = run([0xF8, 0x18, 0x69, 0x01, RTL], a=0x09)

        self.assertEqual(cpu.a & 0xFF, 0x10)

    def test_decimal_subtraction_borrows_at_zero(self):
        cpu = run([0xF8, 0x38, 0xE9, 0x01, RTL], a=0x10)

        self.assertEqual(cpu.a & 0xFF, 0x09)

    def test_a_comparison_sets_the_carry_when_it_is_not_below(self):
        cpu = run([0xC9, 0x10, RTL], a=0x20)

        self.assertTrue(cpu.c)
        self.assertFalse(cpu.z)

    def test_a_comparison_of_equals_sets_zero(self):
        cpu = run([0xC9, 0x20, RTL], a=0x20)

        self.assertTrue(cpu.z)
        self.assertTrue(cpu.c)


class ShiftTest(unittest.TestCase):
    def test_a_shift_left_moves_the_top_bit_into_the_carry(self):
        cpu = run([0x0A, RTL], a=0x81)

        self.assertEqual(cpu.a & 0xFF, 0x02)
        self.assertTrue(cpu.c)

    def test_a_shift_right_moves_the_bottom_bit_into_the_carry(self):
        cpu = run([0x4A, RTL], a=0x03)

        self.assertEqual(cpu.a & 0xFF, 0x01)
        self.assertTrue(cpu.c)

    def test_a_rotate_left_brings_the_carry_in(self):
        cpu = run([0x38, 0x2A, RTL], a=0x00)

        self.assertEqual(cpu.a & 0xFF, 0x01)

    def test_a_rotate_right_brings_the_carry_into_the_top(self):
        cpu = run([0x38, 0x6A, RTL], a=0x00)

        self.assertEqual(cpu.a & 0xFF, 0x80)

    def test_a_shift_in_memory_writes_the_result_back(self):
        memory = FlatMemory({0x000042: 0x40})

        run([0x06, 0x42, RTL], memory=memory)

        self.assertEqual(memory.read8(0x000042), 0x80)

    def test_the_accumulator_half_swaps(self):
        cpu = run([0xEB, RTL], a=0x1234)

        self.assertEqual(cpu.a, 0x3412)


class StackTest(unittest.TestCase):
    def test_pushes_and_pulls_balance(self):
        cpu = run([0x08, 0x8B, 0x48, 0x68, 0xAB, 0x28, RTL], s=0x01FF)

        self.assertEqual(cpu.s, 0x01FF)

    def test_a_wide_push_moves_the_pointer_by_two(self):
        cpu = run([0x48, RTL], status=NATIVE_16, s=0x01FF, a=0x1234)

        self.assertEqual(cpu.s, 0x01FD)

    def test_a_pushed_value_comes_back(self):
        cpu = run([0x48, 0xA9, 0x00, 0x68, RTL], s=0x01FF, a=0x5A)

        self.assertEqual(cpu.a & 0xFF, 0x5A)

    def test_the_direct_register_round_trips_through_the_stack(self):
        cpu = run([0x0B, 0x2B, RTL], status=NATIVE_16, d=0x1234)

        self.assertEqual(cpu.d, 0x1234)

    def test_an_effective_address_can_be_pushed(self):
        cpu = run([0xF4, 0x34, 0x12, RTL], status=NATIVE_16, s=0x01FF)

        self.assertEqual(cpu.s, 0x01FD)


class BlockMoveTest(unittest.TestCase):
    def test_a_forward_move_copies_every_byte(self):
        memory = FlatMemory({0x7E0000 + i: i for i in range(4)})

        run(
            [0xA9, 0x03, 0x00, 0xA2, 0x00, 0x00, 0xA0, 0x00, 0x10, 0x54, 0x7F, 0x7E, RTL],
            memory=memory,
            status=NATIVE_16,
        )

        self.assertEqual([memory.read8(0x7F1000 + i) for i in range(4)], [0, 1, 2, 3])

    def test_a_forward_move_leaves_the_accumulator_at_minus_one(self):
        memory = FlatMemory()

        cpu = run(
            [0xA9, 0x01, 0x00, 0xA2, 0x00, 0x00, 0xA0, 0x00, 0x10, 0x54, 0x7F, 0x7E, RTL],
            memory=memory,
            status=NATIVE_16,
        )

        self.assertEqual(cpu.a, 0xFFFF)

    def test_a_forward_move_advances_both_index_registers(self):
        memory = FlatMemory()

        cpu = run(
            [0xA9, 0x01, 0x00, 0xA2, 0x00, 0x00, 0xA0, 0x00, 0x10, 0x54, 0x7F, 0x7E, RTL],
            memory=memory,
            status=NATIVE_16,
        )

        self.assertEqual(cpu.x, 0x0002)
        self.assertEqual(cpu.y, 0x1002)

    def test_a_move_sets_the_data_bank_to_its_destination(self):
        memory = FlatMemory()

        cpu = run(
            [0xA9, 0x00, 0x00, 0xA2, 0x00, 0x00, 0xA0, 0x00, 0x10, 0x54, 0x7F, 0x7E, RTL],
            memory=memory,
            status=NATIVE_16,
        )

        self.assertEqual(cpu.db, 0x7F)


class ControlTest(unittest.TestCase):
    def test_a_taken_branch_moves_the_program_counter_forward(self):
        cpu = run([0xA9, 0x00, 0xF0, 0x01, 0xEA, RTL])

        self.assertEqual(cpu.pc, 0x8005)

    def test_an_untaken_branch_falls_through(self):
        cpu = run([0xA9, 0x01, 0xF0, 0x01, 0xEA, RTL])

        self.assertEqual(cpu.pc, 0x8005)

    def test_a_branch_reaches_backwards(self):
        cpu = run([0xA2, 0x02, 0xCA, 0xD0, 0xFD, RTL])

        self.assertEqual(cpu.x, 0x00)

    def test_a_subroutine_returns_to_its_caller(self):
        cpu = run([0x20, 0x06, 0x80, 0xA9, 0x11, RTL, 0xA9, 0x22, 0x60], a=0x00)

        self.assertEqual(cpu.a & 0xFF, 0x11)

    def test_a_long_subroutine_returns_across_banks(self):
        memory = FlatMemory({0x018000: 0xA9, 0x018001: 0x33, 0x018002: 0x6B})

        cpu = run([0x22, 0x00, 0x80, 0x01, RTL], memory=memory)

        self.assertEqual(cpu.a & 0xFF, 0x33)


class EmulationModeTest(unittest.TestCase):
    def test_the_carry_and_the_emulation_flag_swap(self):
        cpu = run([0x38, 0xFB, RTL])

        self.assertTrue(cpu.emulation)
        self.assertFalse(cpu.c)

    def test_emulation_mode_forces_eight_bit_registers(self):
        cpu = run([0xC2, 0x30, 0x38, 0xFB, RTL])

        self.assertTrue(cpu.m8)
        self.assertTrue(cpu.x8)

    def test_leaving_emulation_mode_restores_the_carry(self):
        cpu = run([0x38, 0xFB, 0x18, 0xFB, RTL])

        self.assertFalse(cpu.emulation)


class HaltTest(unittest.TestCase):
    def test_stopping_the_processor_refuses_another_step(self):
        memory = FlatMemory({0x008000: 0xDB})
        cpu = emu.Cpu(memory)
        cpu.pb, cpu.pc = 0x00, 0x8000
        cpu.step()

        with self.assertRaises(emu.Stopped):
            cpu.step()

    def test_a_runaway_program_stops_at_the_step_limit(self):
        memory = FlatMemory({0x008000: 0x80, 0x008001: 0xFE})
        cpu = emu.Cpu(memory, step_limit=100)
        cpu.pb, cpu.pc = 0x00, 0x8000

        with self.assertRaises(emu.StepLimit):
            cpu.run_until(lambda machine: False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
