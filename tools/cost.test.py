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
    """Reading the label table the assembler emits."""

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
    """What the harness lets a measured routine reach."""

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
    """What the same exchange cost when a chip answered it."""

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
    """The comparison, and the status it reports."""

    def test_a_command_no_slower_than_retail_passes(self) -> None:
        said: list[str] = []

        code = cost.report({"tile": [(100, 200, True)]}, said.append)

        self.assertEqual((code, "0.50x" in "\n".join(said)), (0, True))

    def test_a_command_slower_than_retail_fails(self) -> None:
        code = cost.report({"tile": [(400, 200, True)]}, lambda _l: None)

        self.assertEqual(code, 1)

    def test_the_line_names_how_many_answers_were_right(self) -> None:
        said: list[str] = []

        cost.report({"tile": [(100, 200, True), (100, 200, False)]}, said.append)

        self.assertIn("1/2", "\n".join(said))

    def test_every_command_gets_a_line(self) -> None:
        said: list[str] = []

        cost.report({"tile": [(1, 2, True)], "merge": [(1, 2, True)]}, said.append)

        self.assertEqual(len(said), 3)

    def test_a_retail_cost_of_nothing_is_not_a_division(self) -> None:
        code = cost.report({"sync": [(10, 0, True)]}, lambda _l: None)

        self.assertEqual(code, 0)


class CommandTest(unittest.TestCase):
    """The command line, without a built cartridge on this machine."""

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


def recorded() -> bytes:
    """A trace holding one whole exchange, so a run has something to measure.

    The transparent command is used because it is the shortest the cartridge
    ever sends: one command byte and one parameter, with nothing to read back.
    Three of them arrive so a quota can be reached and exceeded, and two syncs
    sit among them so the same is true of the command that computes nothing.
    Neither sync ends the stream, because a transaction is closed by whatever
    follows it and one left at the end would be recorded as incomplete.
    """
    import dsptrace

    rows = [
        (0x0F, dsptrace.KIND_WRITE),
        (0x03, dsptrace.KIND_WRITE),
        (0x0A, dsptrace.KIND_WRITE),
        (0x0F, dsptrace.KIND_WRITE),
        (0x03, dsptrace.KIND_WRITE),
        (0x0A, dsptrace.KIND_WRITE),
        (0x03, dsptrace.KIND_WRITE),
        (0x0A, dsptrace.KIND_WRITE),
    ]
    blob = bytearray()
    for byte, kind in rows:
        blob += dsptrace.RECORD.pack(
            1, 0x008000, 0, 0, kind, byte, b"\x00" * 8, 0x00, 0x30, b"\x00" * 4
        )
    return bytes(blob)


RTL = 0x6B
"""One instruction, which is all a measured call needs to return from."""


def cartridge(routines: dict[int, bytes]) -> bytes:
    """A cartridge carrying only what a measurement has to run.

    The harness reads through the LoROM window, so a routine is written at the
    file offset that window reaches, and everything else is left as the $FF a
    blank cartridge holds.
    """
    rom = bytearray(b"\xff" * 0x100000)
    for address, code in routines.items():
        bank, offset = (address >> 16) & 0x7F, address & 0xFFFF
        at = bank * cost.BANK + (offset - cost.BANK)
        rom[at : at + len(code)] = code
    return bytes(rom)


class MachineTest(unittest.TestCase):
    """A processor with a cartridge behind it."""

    def test_it_starts_out_of_emulation_mode(self) -> None:
        cpu, _ = cost.machine(cartridge({}))

        self.assertFalse(cpu.emulation)

    def test_the_cartridge_is_what_the_window_reads(self) -> None:
        _, memory = cost.machine(cartridge({0x9CE000: bytes([0xAB])}))

        self.assertEqual(memory.read8(0x9CE000), 0xAB)


class EnterTest(unittest.TestCase):
    """Running one call and counting what it spent."""

    def test_a_routine_that_returns_at_once_costs_what_the_return_costs(self) -> None:
        cpu, _ = cost.machine(cartridge({0x9CE000: bytes([RTL])}))

        self.assertEqual(cost.enter(cpu, 0x9CE000), 6)

    def test_a_longer_routine_costs_more(self) -> None:
        rom = cartridge({0x9CE000: bytes([RTL]), 0x9CE100: bytes([0xEA, 0xEA, RTL])})
        cpu, _ = cost.machine(rom)

        short = cost.enter(cpu, 0x9CE000)

        self.assertLess(short, cost.enter(cpu, 0x9CE100))

    def test_a_routine_that_never_returns_is_refused_rather_than_run_forever(self) -> None:
        cpu, _ = cost.machine(cartridge({0x9CE000: bytes([0x80, 0xFE])}))

        with self.assertRaises(cost.Ran):
            cost.enter(cpu, 0x9CE000, limit=50)


class MeasureTest(unittest.TestCase):
    """Delivering one exchange the way the cartridge delivers it."""

    def names(self) -> dict[str, int]:
        return {
            "dsp_write": 0x9CE000,
            "dsp_feed_wram": 0x9CE000,
            "dsp_drain_wram": 0x9CE000,
        }

    def machine(self) -> Any:
        return cost.machine(cartridge({0x9CE000: bytes([RTL])}))

    def test_a_command_with_no_payload_costs_one_call(self) -> None:
        cpu, memory = self.machine()

        self.assertEqual(cost.measure(cpu, memory, self.names(), 0x03, (), b"", 0), 6)

    def test_each_declared_length_costs_another_call(self) -> None:
        cpu, memory = self.machine()

        self.assertEqual(cost.measure(cpu, memory, self.names(), 0x05, (4,), b"", 0), 12)

    def test_a_payload_is_delivered_in_one_block_move(self) -> None:
        cpu, memory = self.machine()

        self.assertEqual(cost.measure(cpu, memory, self.names(), 0x01, (), bytes(32), 0), 12)

    def test_the_payload_is_staged_where_the_block_move_reads_it(self) -> None:
        cpu, memory = self.machine()

        cost.measure(cpu, memory, self.names(), 0x01, (), bytes([0xAB]) * 4, 0)

        self.assertEqual(memory.read8(cost.SOURCE), 0xAB)

    def test_a_result_is_drained_in_one_block_move(self) -> None:
        cpu, memory = self.machine()

        self.assertEqual(cost.measure(cpu, memory, self.names(), 0x01, (), b"", 32), 12)


class ProducedTest(unittest.TestCase):
    """Reading back what the replacement drained."""

    def test_it_reads_from_where_the_drain_was_told_to_write(self) -> None:
        _, memory = cost.machine(cartridge({}))
        memory.write8(cost.DESTINATION, 0x5A)

        self.assertEqual(cost.produced(memory, 1), bytes([0x5A]))

    def test_a_result_of_no_length_is_no_bytes(self) -> None:
        _, memory = cost.machine(cartridge({}))

        self.assertEqual(cost.produced(memory, 0), b"")


class WholeRunTest(unittest.TestCase):
    """The command line, over a cartridge and a trace made for the occasion."""

    def setUpFiles(self) -> tuple[Path, Path, Path]:
        where = Path(tempfile.mkdtemp())
        rom = where / "probe.sfc"
        rom.write_bytes(cartridge({0x9CE000: bytes([RTL])}))
        (where / "probe.sym").write_text(
            "[labels]\n9C:E000 dsp_init\n9C:E000 dsp_write\n"
            "9C:E000 dsp_feed_wram\n9C:E000 dsp_drain_wram\n"
        )
        trace = where / "trace.bin"
        trace.write_bytes(recorded())
        return rom, where / "probe.sym", trace

    def test_a_run_reports_one_line_per_command_it_saw(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "1"], said.append)

        self.assertTrue(any("transparent" in one for one in said))

    def test_sampling_stops_once_every_command_has_been_seen_enough(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "1"], said.append, ("transparent",))

        self.assertIn("       1", said[1])

    def test_a_command_seen_enough_is_passed_over_while_others_are_still_wanted(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "2"], said.append)

        self.assertIn("       2", said[1])

    def test_and_prices_it_against_what_the_chip_path_cost(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "1"], said.append)

        self.assertIn("1/1", "\n".join(said))

    def test_the_handshake_is_priced_rather_than_passed_over(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "1"], said.append)

        self.assertTrue(any(one.strip().startswith("sync") for one in said))

    def test_an_exchange_the_trace_never_finished_is_left_out(self) -> None:
        import dsptrace

        rom, sym, trace = self.setUpFiles()
        trace.write_bytes(recorded()[: -dsptrace.RECORD_BYTES])
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "9"], said.append)

        self.assertIn("      2", said[2])


if __name__ == "__main__":
    unittest.main()
