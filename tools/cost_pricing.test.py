import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_module(name: str, where: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, where / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cost = load_module("cost", ROOT / "tools")
SYMBOLS = "; a comment\n[labels]\n9C:E1BF dsp_init\n9C:E202 dsp_write\n00:FBED :local\n"


class SymbolTest(unittest.TestCase):
    def test_a_label_becomes_a_twenty_four_bit_address(self) -> None:
        self.assertEqual(cost.symbols(SYMBOLS)["dsp_init"], 0x9CE1BF)

    def test_every_label_in_the_table_is_read(self) -> None:
        self.assertEqual(sorted(cost.symbols(SYMBOLS)), ["dsp_init", "dsp_write"])

    def test_a_comment_is_not_a_label(self) -> None:
        self.assertNotIn("a", cost.symbols(SYMBOLS))

    def test_a_local_label_is_left_out(self) -> None:
        self.assertNotIn(":local", cost.symbols(SYMBOLS))

    def test_a_line_whose_address_is_not_a_number_is_left_out(self) -> None:
        self.assertEqual(cost.symbols("[labels]\nzz:zzzz nonsense\n"), {})


class MemoryTest(unittest.TestCase):
    def machine(self) -> Any:
        return cost.LoRom(bytes(range(256)) * 4096)

    def test_work_ram_reads_back_what_was_written(self) -> None:
        memory = self.machine()
        memory.write8(0x7E0900, 0xAB)

        self.assertEqual(memory.read8(0x7E0900), 0xAB)

    def test_the_second_work_ram_bank_is_its_own_storage(self) -> None:
        memory = self.machine()
        memory.write8(0x7E0900, 0xAB)
        memory.write8(0x7F0900, 0xCD)

        self.assertEqual(memory.read8(0x7E0900), 0xAB)

    def test_the_low_half_of_bank_zero_mirrors_work_ram(self) -> None:
        memory = self.machine()
        memory.write8(0x7E0A00, 0x5A)

        self.assertEqual(memory.read8(0x000A00), 0x5A)

    def test_the_cartridge_answers_through_the_lorom_window(self) -> None:
        memory = self.machine()

        self.assertEqual(memory.read8(0x008000), 0x00)

    def test_the_multiplier_returns_the_product_of_what_it_was_given(self) -> None:
        memory = self.machine()
        memory.write8(0x004202, 0x10)
        memory.write8(0x004203, 0x20)

        self.assertEqual(memory.read8(0x004216), 0x00)

    def test_and_its_high_byte(self) -> None:
        memory = self.machine()
        memory.write8(0x004202, 0x10)
        memory.write8(0x004203, 0x20)

        self.assertEqual(memory.read8(0x004217), 0x02)

    def test_a_register_this_does_not_model_is_refused_rather_than_answered(self) -> None:
        with self.assertRaises(cost.Ran):
            self.machine().read8(0x004210)

    def test_and_a_write_to_one_is_refused_too(self) -> None:
        with self.assertRaises(cost.Ran):
            self.machine().write8(0x004210, 0x00)

    def test_the_registers_the_boot_code_sets_are_accepted_and_ignored(self) -> None:
        memory = self.machine()

        memory.write8(0x00420D, 0x01)

        self.assertEqual(memory.read8(0x008000), 0x00)


class RetailCostTest(unittest.TestCase):
    def test_a_payload_is_priced_at_the_block_move_rate(self) -> None:
        found = cost.retail_cost("tile", bytes(32), bytes(32))

        self.assertEqual(found, cost.LONG_ACCESS_CYCLES + 64 * cost.MOVE_CYCLES_PER_BYTE)

    def test_a_command_that_declares_a_length_pays_for_that_store_too(self) -> None:
        one = cost.retail_cost("tile", bytes(4), bytes(4))
        two = cost.retail_cost("merge", bytes(4), bytes(4))

        self.assertEqual(two - one, cost.LONG_ACCESS_CYCLES)

    def test_the_scale_command_declares_two_lengths(self) -> None:
        one = cost.retail_cost("tile", bytes(4), bytes(4))
        two = cost.retail_cost("scale", bytes(4), bytes(4))

        self.assertEqual(two - one, 2 * cost.LONG_ACCESS_CYCLES)

    def test_a_longer_payload_costs_more(self) -> None:
        short = cost.retail_cost("merge", bytes(20), bytes(10))
        long = cost.retail_cost("merge", bytes(60), bytes(30))

        self.assertGreater(long, short)


class ReportTest(unittest.TestCase):
    def test_a_command_slower_than_retail_still_passes(self) -> None:
        said: list[str] = []

        code = cost.report({"tile": [(400, 440, 200, True)]}, said.append)

        self.assertEqual((code, "2.00x" in "\n".join(said)), (0, True))

    def test_the_ratio_is_reported_either_way(self) -> None:
        said: list[str] = []

        cost.report({"tile": [(100, 140, 200, True)]}, said.append)

        self.assertIn("0.50x", "\n".join(said))

    def test_a_command_that_answered_wrongly_fails(self) -> None:
        said: list[str] = []

        code = cost.report({"tile": [(100, 140, 200, False)]}, said.append)

        self.assertEqual(code, 1)
        self.assertTrue(any("did not match" in one for one in said))

    def test_and_says_how_many_of_them_did(self) -> None:
        said: list[str] = []

        cost.report({"tile": [(1, 2, 3, False)], "merge": [(1, 2, 3, False)]}, said.append)

        self.assertTrue(any("2 answers" in one for one in said))

    def test_the_line_names_how_many_answers_were_right(self) -> None:
        said: list[str] = []

        cost.report({"tile": [(100, 140, 200, True), (100, 140, 200, False)]}, said.append)

        self.assertIn("1/2", "\n".join(said))

    def test_every_command_gets_a_line(self) -> None:
        said: list[str] = []

        cost.report({"tile": [(1, 2, 3, True)], "merge": [(1, 2, 3, True)]}, said.append)

        self.assertEqual(len(said), 3)

    def test_a_retail_cost_of_nothing_is_not_a_division(self) -> None:
        code = cost.report({"sync": [(10, 12, 0, True)]}, lambda _l: None)

        self.assertEqual(code, 0)


class CommandTest(unittest.TestCase):
    def test_a_missing_cartridge_is_reported_rather_than_opened(self) -> None:
        said: list[str] = []

        code = cost.main(["cost.py", "/nonexistent/rom.sfc", "/nonexistent/rom.sym"], said.append)

        self.assertEqual((code, "build" in said[0]), (2, True))

    def test_symbols_older_than_the_cartridge_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            (where / "probe.sym").write_text("[labels]\n9C:E000 dsp_init\n")
            (where / "probe.sfc").write_bytes(b"\x00")
            os.utime(where / "probe.sym", (0, 0))
            said: list[str] = []

            code = cost.main(
                ["cost.py", str(where / "probe.sfc"), str(where / "probe.sym")], said.append
            )

        self.assertEqual((code, "older" in said[0]), (2, True))


if __name__ == "__main__":
    unittest.main()
