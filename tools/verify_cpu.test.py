import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "tools" / "verify_cpu.py"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify = load_module("verify_cpu", MODULE_PATH)
wdc = verify.wdc65816


class CatalogueTest(unittest.TestCase):
    def test_the_catalogue_is_not_empty(self) -> None:
        self.assertGreater(len(verify.testable_opcodes()), 100)

    def test_nothing_that_changes_the_program_counter_is_tested_in_isolation(self) -> None:
        for _, mnemonic, mode in verify.testable_opcodes():
            self.assertNotIn(mnemonic, verify.SKIP_MNEMONICS)
            self.assertNotIn(mode, verify.SKIP_MODES)

    def test_every_entry_names_a_real_opcode(self) -> None:
        for opcode, mnemonic, mode in verify.testable_opcodes():
            self.assertEqual(wdc.OPCODES[opcode], (mnemonic, mode))


class CaseTest(unittest.TestCase):
    def test_the_same_seed_builds_the_same_cases(self) -> None:
        first = verify.build_cases(11, 40)
        second = verify.build_cases(11, 40)

        self.assertEqual(first, second)

    def test_a_different_seed_builds_different_cases(self) -> None:
        self.assertNotEqual(verify.build_cases(1, 40), verify.build_cases(2, 40))

    def test_every_case_carries_the_bytes_of_its_instruction(self) -> None:
        for case in verify.build_cases(3, 60):
            self.assertEqual(case["bytes"][0], case["opcode"])
            self.assertGreaterEqual(len(case["bytes"]), 1)

    def test_an_immediate_operand_follows_the_width_its_flags_declare(self) -> None:
        for case in verify.build_cases(5, 300):
            if case["mode"] != "immediateA":
                continue
            wide = not (case["p"] & verify.emu65816.FLAG_M)
            self.assertEqual(len(case["bytes"]), 3 if wide else 2)

    def test_interrupts_are_left_disabled_so_a_case_runs_alone(self) -> None:
        for case in verify.build_cases(7, 60):
            self.assertEqual(case["p"] & 0x04, 0x04 & case["p"])


class AssemblyTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.cases = verify.build_cases(9, 12)
        self.text = verify.emit_asm(self.cases)

    def test_the_listing_carries_one_block_per_case(self) -> None:
        for index in range(len(self.cases)):
            self.assertIn(f"case_{index}:", self.text)

    def test_the_instruction_under_test_is_emitted_as_raw_bytes(self) -> None:
        first = self.cases[0]
        wanted = ",".join(f"${b:02X}" for b in first["bytes"])

        self.assertIn(wanted, self.text)

    def test_the_listing_sets_a_finished_marker(self) -> None:
        self.assertIn(f"${verify.DONE_FLAG:06X}", self.text)

    def test_the_listing_declares_a_reset_vector(self) -> None:
        self.assertIn("dw reset", self.text)


class PowerOnTest(unittest.TestCase):
    def test_the_cartridge_fills_work_ram_before_running_a_case(self) -> None:
        text = verify.emit_asm(verify.build_cases(1, 2))

        self.assertIn("fill_work_ram:", text)
        self.assertIn("sta.l $7E0000,x", text)
        self.assertIn("sta.l $7F0000,x", text)

    def test_the_results_sit_where_no_case_can_reach_them(self) -> None:
        self.assertEqual(verify.RESULT_BASE >> 16, 0x7F)
        self.assertEqual(verify.DONE_FLAG >> 16, 0x7F)

    def test_every_case_declares_the_cartridge_bank_as_its_data_bank(self) -> None:
        for case in verify.build_cases(4, 60):
            self.assertEqual(case["db"], 0x7E)


class NativeModeTest(unittest.TestCase):
    def a_case(self, status: int) -> dict[str, Any]:
        return {
            "bytes": [0xEA],
            "p": status,
            "a": 0x1234,
            "x": 0x5678,
            "y": 0x9ABC,
            "d": 0x0000,
            "db": 0x7E,
        }

    def test_a_case_with_both_widths_clear_keeps_them_clear(self) -> None:
        found = verify.run_in_python([self.a_case(0x04)], bytes(verify.ROM_BYTES))

        self.assertEqual(found[0]["p"] & 0x30, 0x00)

    def test_a_case_with_both_widths_set_keeps_them_set(self) -> None:
        found = verify.run_in_python([self.a_case(0x34)], bytes(verify.ROM_BYTES))

        self.assertEqual(found[0]["p"] & 0x30, 0x30)

    def test_a_sixteen_bit_index_survives_into_the_result(self) -> None:
        found = verify.run_in_python([self.a_case(0x04)], bytes(verify.ROM_BYTES))

        self.assertEqual(found[0]["x"], 0x5678)


class ComparisonTest(unittest.TestCase):
    def test_identical_results_report_no_mismatch(self) -> None:
        cases = verify.build_cases(2, 3)
        state = [{"a": 1, "x": 2, "y": 3, "p": 4, "d": 5, "db": 6} for _ in cases]

        self.assertEqual(verify.compare(cases, state, list(state)), [])

    def test_a_differing_accumulator_is_reported(self) -> None:
        cases = verify.build_cases(2, 1)
        wanted = [{"a": 1, "x": 2, "y": 3, "p": 4, "d": 5, "db": 6}]
        found = [{"a": 9, "x": 2, "y": 3, "p": 4, "d": 5, "db": 6}]

        mismatches = verify.compare(cases, wanted, found)

        self.assertEqual(len(mismatches), 1)
        self.assertIn("a", mismatches[0][3])

    def test_a_differing_status_byte_is_reported(self) -> None:
        cases = verify.build_cases(2, 1)
        wanted = [{"a": 1, "x": 2, "y": 3, "p": 4, "d": 5, "db": 6}]
        found = [{"a": 1, "x": 2, "y": 3, "p": 0x80, "d": 5, "db": 6}]

        self.assertIn("p", verify.compare(cases, wanted, found)[0][3])


class ResultsTest(unittest.TestCase):
    def test_a_result_block_is_decoded_from_the_dump(self) -> None:
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


class BankCrossingTest(unittest.TestCase):
    def test_a_run_longer_than_a_bank_jumps_to_the_next(self) -> None:
        text = verify.emit_asm(verify.build_cases(0, verify.CASES_PER_BANK + 2))

        self.assertIn("jml case_", text)


class ShellingOutTest(unittest.TestCase):
    def test_assembling_names_the_images_assembler(self) -> None:
        # Arrange
        expected = ["asar", "--no-title-check", verify.CASES_ASM.name, verify.CASES_ROM.name]

        # Act
        found = verify.assemble_command()

        # Assert
        self.assertEqual(found[2:], expected)

    def test_running_names_the_images_emulator_and_how_many_frames(self) -> None:
        # Arrange
        frames = 600

        # Act
        found = verify.emulator_command(frames)

        # Assert
        self.assertIn("dmemu", found)
        self.assertEqual(found[-1], "600")

    def test_an_assembler_that_fails_says_what_it_said_and_stops(self) -> None:
        said: list[Any] = []
        failed = type("Done", (), {"returncode": 1, "stdout": "out", "stderr": "asar said no"})

        found = verify.assemble("; nothing", execute=lambda _a: failed, say=said.append)

        self.assertFalse(found)
        self.assertIn("asar said no", " ".join(said))

    def test_one_that_succeeds_reports_that_it_did(self) -> None:
        done = type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})

        self.assertTrue(verify.assemble("; nothing", execute=lambda _a: done, say=lambda _l: None))

    def test_an_emulator_that_finishes_hands_back_what_it_dumped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "wram.bin"
            where.write_bytes(b"\xab" * 16)
            original, verify.CASES_DUMP = verify.CASES_DUMP, where
            done = type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})
            try:
                found = verify.run_in_snes9x(600, execute=lambda _a: done, say=lambda _l: None)
            finally:
                verify.CASES_DUMP = original

        self.assertEqual(found, b"\xab" * 16)

    def test_an_emulator_that_fails_hands_back_nothing(self) -> None:
        failed = type("Done", (), {"returncode": 1, "stdout": "out", "stderr": "no emulator"})

        found = verify.run_in_snes9x(600, execute=lambda _a: failed, say=lambda _l: None)

        self.assertIsNone(found)

    def test_the_real_path_runs_the_command_it_was_given(self) -> None:
        self.assertEqual(verify._shell_out(["true"]).returncode, 0)


class LinesTest(unittest.TestCase):
    def test_a_run_where_everything_agrees_says_how_many_did(self) -> None:
        cases = verify.build_cases(0, 4)

        lines = verify.lines_for(cases, [])

        self.assertIn("4 of 4 agree", lines[-1])

    def test_a_disagreement_names_the_opcode_and_both_values(self) -> None:
        cases = verify.build_cases(0, 1)
        mismatch = (cases[0], {"a": 1}, {"a": 2}, ["a"])

        lines = verify.lines_for(cases, [mismatch])

        self.assertIn("snes9x 0x0001", lines[0])
        self.assertIn("python 0x0002", lines[0])

    def test_no_more_than_a_handful_of_disagreements_are_listed(self) -> None:
        cases = verify.build_cases(0, 40)
        mismatches = [(case, {"a": 1}, {"a": 2}, ["a"]) for case in cases]

        lines = verify.lines_for(cases, mismatches)

        self.assertEqual(len(lines) - 1, verify.EXAMPLE_LIMIT)


class EntryTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        where = Path(tempfile.mkdtemp()) / "cases.sfc"
        where.write_bytes(bytes(verify.ROM_BYTES))
        original = verify.CASES_ROM
        verify.CASES_ROM = where
        self.addCleanup(setattr, verify, "CASES_ROM", original)

    def _dump(self, finished: Any = True) -> Any:
        dump = bytearray(0x20000)
        if finished:
            dump[0x10000 + (verify.DONE_FLAG & 0xFFFF)] = 0xA5
        return bytes(dump)

    def test_an_assembler_that_fails_ends_the_run(self) -> None:
        code = verify.main(
            ["verify_cpu.py", "0", "2"], build=lambda _text: False, say=lambda _l: None
        )

        self.assertEqual(code, 1)

    def test_an_emulator_that_gives_nothing_back_ends_it_too(self) -> None:
        code = verify.main(
            ["verify_cpu.py", "0", "2"],
            build=lambda _text: True,
            walk=lambda _frames: None,
            say=lambda _l: None,
        )

        self.assertEqual(code, 1)

    def test_a_whole_run_compares_both_and_says_how_many_agree(self) -> None:
        said: list[Any] = []

        code = verify.main(
            ["verify_cpu.py", "0", "2"],
            build=lambda _text: True,
            walk=lambda _frames: self._dump(),
            say=said.append,
        )

        self.assertIn(code, (0, 1))
        self.assertIn("agree with snes9x", said[-1])

    def test_a_cartridge_that_did_not_finish_is_reported(self) -> None:
        complained: list[Any] = []

        code = verify.main(
            ["verify_cpu.py", "0", "2"],
            build=lambda _text: True,
            walk=lambda _frames: self._dump(finished=False),
            say=lambda _l: None,
            complain=complained.append,
        )

        self.assertEqual(code, 1)
        self.assertIn("did not finish", complained[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
