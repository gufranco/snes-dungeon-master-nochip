import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "tools" / "verify_cpu.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify = load_module("verify_cpu", MODULE_PATH)
wdc = verify.wdc65816


class CatalogueTest(unittest.TestCase):
    def test_the_catalogue_is_not_empty(self):
        self.assertGreater(len(verify.testable_opcodes()), 100)

    def test_nothing_that_changes_the_program_counter_is_tested_in_isolation(self):
        for _, mnemonic, mode in verify.testable_opcodes():
            self.assertNotIn(mnemonic, verify.SKIP_MNEMONICS)
            self.assertNotIn(mode, verify.SKIP_MODES)

    def test_every_entry_names_a_real_opcode(self):
        for opcode, mnemonic, mode in verify.testable_opcodes():
            self.assertEqual(wdc.OPCODES[opcode], (mnemonic, mode))


class CaseTest(unittest.TestCase):
    def test_the_same_seed_builds_the_same_cases(self):
        first = verify.build_cases(11, 40)
        second = verify.build_cases(11, 40)

        self.assertEqual(first, second)

    def test_a_different_seed_builds_different_cases(self):
        self.assertNotEqual(verify.build_cases(1, 40), verify.build_cases(2, 40))

    def test_every_case_carries_the_bytes_of_its_instruction(self):
        for case in verify.build_cases(3, 60):
            self.assertEqual(case["bytes"][0], case["opcode"])
            self.assertGreaterEqual(len(case["bytes"]), 1)

    def test_an_immediate_operand_follows_the_width_its_flags_declare(self):
        for case in verify.build_cases(5, 300):
            if case["mode"] != "immediateA":
                continue
            wide = not (case["p"] & verify.emu65816.FLAG_M)
            self.assertEqual(len(case["bytes"]), 3 if wide else 2)

    def test_interrupts_are_left_disabled_so_a_case_runs_alone(self):
        for case in verify.build_cases(7, 60):
            self.assertEqual(case["p"] & 0x04, 0x04 & case["p"])


class AssemblyTest(unittest.TestCase):
    def setUp(self):
        self.cases = verify.build_cases(9, 12)
        self.text = verify.emit_asm(self.cases)

    def test_the_listing_carries_one_block_per_case(self):
        for index in range(len(self.cases)):
            self.assertIn(f"case_{index}:", self.text)

    def test_the_instruction_under_test_is_emitted_as_raw_bytes(self):
        first = self.cases[0]
        wanted = ",".join(f"${b:02X}" for b in first["bytes"])

        self.assertIn(wanted, self.text)

    def test_the_listing_sets_a_finished_marker(self):
        self.assertIn(f"${verify.DONE_FLAG:06X}", self.text)

    def test_the_listing_declares_a_reset_vector(self):
        self.assertIn("dw reset", self.text)


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.memory = verify.LoRomMemory(bytes(range(256)) * 1024)

    def test_work_ram_reads_back_what_was_written(self):
        self.memory.write8(0x7E1234, 0xA5)

        self.assertEqual(self.memory.read8(0x7E1234), 0xA5)

    def test_low_work_ram_is_mirrored_into_the_low_banks(self):
        self.memory.write8(0x7E0123, 0x5A)

        self.assertEqual(self.memory.read8(0x000123), 0x5A)

    def test_the_cartridge_is_read_only(self):
        before = self.memory.read8(0x008000)

        self.memory.write8(0x008000, before ^ 0xFF)

        self.assertEqual(self.memory.read8(0x008000), before)

    def test_a_lorom_address_maps_to_its_linear_offset(self):
        rom = bytearray(0x80000)
        rom[0x8000] = 0x42
        memory = verify.LoRomMemory(bytes(rom))

        self.assertEqual(memory.read8(0x018000), 0x42)


class PowerOnTest(unittest.TestCase):
    def test_the_cartridge_fills_work_ram_before_running_a_case(self):
        text = verify.emit_asm(verify.build_cases(1, 2))

        self.assertIn("fill_work_ram:", text)
        self.assertIn("sta.l $7E0000,x", text)
        self.assertIn("sta.l $7F0000,x", text)

    def test_the_results_sit_where_no_case_can_reach_them(self):
        self.assertEqual(verify.RESULT_BASE >> 16, 0x7F)
        self.assertEqual(verify.DONE_FLAG >> 16, 0x7F)

    def test_every_case_declares_the_cartridge_bank_as_its_data_bank(self):
        for case in verify.build_cases(4, 60):
            self.assertEqual(case["db"], 0x7E)


class ComparisonTest(unittest.TestCase):
    def test_identical_results_report_no_mismatch(self):
        cases = verify.build_cases(2, 3)
        state = [{"a": 1, "x": 2, "y": 3, "p": 4, "d": 5, "db": 6} for _ in cases]

        self.assertEqual(verify.compare(cases, state, list(state)), [])

    def test_a_differing_accumulator_is_reported(self):
        cases = verify.build_cases(2, 1)
        wanted = [{"a": 1, "x": 2, "y": 3, "p": 4, "d": 5, "db": 6}]
        found = [{"a": 9, "x": 2, "y": 3, "p": 4, "d": 5, "db": 6}]

        mismatches = verify.compare(cases, wanted, found)

        self.assertEqual(len(mismatches), 1)
        self.assertIn("a", mismatches[0][3])

    def test_a_differing_status_byte_is_reported(self):
        cases = verify.build_cases(2, 1)
        wanted = [{"a": 1, "x": 2, "y": 3, "p": 4, "d": 5, "db": 6}]
        found = [{"a": 1, "x": 2, "y": 3, "p": 0x80, "d": 5, "db": 6}]

        self.assertIn("p", verify.compare(cases, wanted, found)[0][3])


class ResultsTest(unittest.TestCase):
    def test_a_result_block_is_decoded_from_the_dump(self):
        dump = bytearray(0x20000)
        at = 0x10000 + (verify.RESULT_BASE & 0xFFFF)
        dump[at : at + 13] = bytes(
            [0x34, 0x12, 0x78, 0x56, 0xBC, 0x9A, 0x30, 0, 0, 0, 0x00, 0x20, 0x7E]
        )

        found = verify.read_results(bytes(dump), 1)[0]

        self.assertEqual(found["a"], 0x1234)
        self.assertEqual(found["x"], 0x5678)
        self.assertEqual(found["y"], 0x9ABC)
        self.assertEqual(found["p"], 0x30)
        self.assertEqual(found["d"], 0x2000)
        self.assertEqual(found["db"], 0x7E)


if __name__ == "__main__":
    unittest.main(verbosity=2)
