import importlib.util
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import script  # noqa: E402


def load_module(name: str, where: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, where / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cost = load_module("cost", ROOT / "tools")

SYMBOLS = "; a comment\n[labels]\n9C:E1BF dsp_init\n9C:E202 dsp_write\n00:FBED :local\n"


SPREAD = 25


def recorded(frame: int = 900) -> bytes:
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
    for step, (byte, kind) in enumerate(rows):
        blob += dsptrace.RECORD.pack(
            frame + step * SPREAD, 0x008000, 0, 0, kind, byte, b"\x00" * 8, 0x00, 0x30, b"\x00" * 4
        )
    return bytes(blob)


RTL = 0x6B


def cartridge(routines: dict[int, bytes]) -> bytes:
    rom = bytearray(b"\xff" * 0x100000)
    for address, code in routines.items():
        bank, offset = (address >> 16) & 0x7F, address & 0xFFFF
        at = bank * cost.BANK + (offset - cost.BANK)
        rom[at : at + len(code)] = code
    return bytes(rom)


class MachineTest(unittest.TestCase):
    def test_it_starts_out_of_emulation_mode(self) -> None:
        cpu, _ = cost.machine(cartridge({}))

        self.assertFalse(cpu.emulation)

    def test_the_cartridge_is_what_the_window_reads(self) -> None:
        _, memory = cost.machine(cartridge({0x9CE000: bytes([0xAB])}))

        self.assertEqual(memory.read8(0x9CE000), 0xAB)


class EnterTest(unittest.TestCase):
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
    def names(self) -> dict[str, int]:
        return {
            "dsp_write": 0x9CE000,
            "dsp_feed_wram": 0x9CE000,
            "dsp_drain_wram": 0x9CE000,
            "tramp_0084": 0x9CE000,
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
    def test_it_reads_from_where_the_drain_was_told_to_write(self) -> None:
        _, memory = cost.machine(cartridge({}))
        memory.write8(cost.DESTINATION, 0x5A)

        self.assertEqual(cost.produced(memory, 1), bytes([0x5A]))

    def test_a_result_of_no_length_is_no_bytes(self) -> None:
        _, memory = cost.machine(cartridge({}))

        self.assertEqual(cost.produced(memory, 0), b"")


class CollectTest(unittest.TestCase):
    def a_trace(self) -> Any:
        import tempfile

        where = Path(tempfile.mkdtemp())
        trace = where / "trace.bin"
        trace.write_bytes(recorded())
        return trace

    def test_it_reads_the_whole_exchanges_the_window_holds(self) -> None:
        found = cost.collect(self.a_trace())

        self.assertEqual(
            [one[0] for one in found],
            ["sync", "transparent", "sync", "transparent", "transparent"],
        )

    def test_it_stops_at_the_bound_it_was_given(self) -> None:
        found = cost.collect(self.a_trace(), limit=1)

        self.assertEqual(len(found), 1)

    def test_nothing_before_the_settled_frame_is_read(self) -> None:
        found = cost.collect(self.a_trace(), after=100_000)

        self.assertEqual(found, [])


class ChosenTest(unittest.TestCase):
    def a_window(self, merges: int, colours: int, scales: int) -> list[Any]:
        found = [("merge", 0) for _ in range(merges)]
        found += [("transparent", 0) for _ in range(colours)]
        found += [("scale", 0) for _ in range(scales)]
        return found

    def test_a_plentiful_command_is_spread_over_the_whole_window(self) -> None:
        found = self.a_window(merges=1000, colours=0, scales=0)

        _replay, record = cost.chosen(found, wanted=10)

        self.assertGreater(max(record) - min(record), 800)

    def test_it_measures_no_more_of_it_than_asked_for(self) -> None:
        found = self.a_window(merges=1000, colours=0, scales=0)

        _replay, record = cost.chosen(found, wanted=10)

        self.assertEqual(len(record), 10)

    def test_a_command_the_window_barely_carries_is_taken_whole(self) -> None:
        found = self.a_window(merges=0, colours=0, scales=3)

        _replay, record = cost.chosen(found, wanted=10)

        self.assertEqual(len(record), 3)

    def test_every_colour_is_replayed_whether_or_not_it_is_measured(self) -> None:
        found = self.a_window(merges=0, colours=40, scales=0)

        replay, record = cost.chosen(found, wanted=5)

        self.assertEqual((len(replay), len(record)), (40, 5))

    def test_what_is_measured_is_always_replayed(self) -> None:
        found = self.a_window(merges=500, colours=20, scales=4)

        replay, record = cost.chosen(found, wanted=10)

        self.assertTrue(set(record) <= set(replay))

    def test_the_order_the_cartridge_used_is_kept(self) -> None:
        found = self.a_window(merges=500, colours=20, scales=4)

        replay, _record = cost.chosen(found, wanted=10)

        self.assertEqual(replay, sorted(replay))


class Scripted:
    asking = True

    def __init__(self, answers: bytes = b"") -> None:
        self.answers = iter(answers)

    def write(self, _byte: int) -> None:
        return None

    def read(self) -> int:
        return next(self.answers, 0)


def scripted(answers: bytes = b"") -> Callable[[str], Scripted]:
    return lambda _name: Scripted(answers)


SILENT_PART: dict[str, Any] = {"build": scripted(), "refuses": lambda: None}

MULTIPLY = 0x09

RECORDED_ANSWER = bytes([0x12, 0x34, 0x56, 0x78])


def recorded_multiply(answer: bytes = RECORDED_ANSWER) -> bytes:
    import dsptrace

    rows = (
        (MULTIPLY, dsptrace.KIND_WRITE),
        *((0x00, dsptrace.KIND_WRITE) for _ in range(4)),
        *((byte, dsptrace.KIND_READ) for byte in answer),
    )
    return b"".join(
        dsptrace.RECORD.pack(900, 0x008000, 0, 0, kind, byte, b"\x00" * 8, 0x00, 0x30, b"\x00" * 4)
        for byte, kind in rows
    )


class WholeRunTest(unittest.TestCase):
    def setUpFiles(self) -> tuple[Path, Path, Path]:
        where = Path(tempfile.mkdtemp())
        rom = where / "probe.sfc"
        rom.write_bytes(cartridge({0x9CE000: bytes([RTL])}))
        (where / "probe.sym").write_text(
            "[labels]\n9C:E000 dsp_init\n9C:E000 dsp_write\n"
            "9C:E000 dsp_feed_wram\n9C:E000 dsp_drain_wram\n9C:E000 tramp_0084\n"
        )
        trace = where / "trace.bin"
        trace.write_bytes(recorded())
        return rom, where / "probe.sym", trace

    def test_a_run_reports_one_line_per_command_it_saw(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "1"], said.append, **SILENT_PART)

        self.assertTrue(any("transparent" in one for one in said))

    def test_sampling_stops_once_every_command_has_been_seen_enough(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(
            ["cost.py", str(rom), str(sym), str(trace), "1"],
            said.append,
            ("transparent",),
            **SILENT_PART,
        )

        self.assertIn("       1", said[1])

    def test_a_command_seen_enough_is_passed_over_while_others_are_still_wanted(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "2"], said.append, **SILENT_PART)

        self.assertIn("       2", said[1])

    def test_and_prices_it_against_what_the_chip_path_cost(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "1"], said.append, **SILENT_PART)

        self.assertIn("1/1", "\n".join(said))

    def test_the_handshake_is_priced_rather_than_passed_over(self) -> None:
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "1"], said.append, **SILENT_PART)

        self.assertTrue(any(one.strip().startswith("sync") for one in said))

    def test_the_boot_sequence_is_not_what_gets_measured(self) -> None:
        rom, sym, trace = self.setUpFiles()
        trace.write_bytes(recorded(frame=0))
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "1"], said.append, **SILENT_PART)

        self.assertFalse(any("transparent" in one for one in said))

    def test_an_exchange_once_the_game_is_playing_is_measured(self) -> None:
        rom, sym, trace = self.setUpFiles()
        trace.write_bytes(recorded(frame=cost.SETTLED_FRAME))
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "1"], said.append, **SILENT_PART)

        self.assertTrue(any("transparent" in one for one in said))

    def test_an_exchange_the_trace_never_finished_is_left_out(self) -> None:
        import dsptrace

        rom, sym, trace = self.setUpFiles()
        trace.write_bytes(recorded()[: -dsptrace.RECORD_BYTES])
        said: list[str] = []

        cost.main(["cost.py", str(rom), str(sym), str(trace), "9"], said.append, **SILENT_PART)

        self.assertIn("      2", said[2])

    def test_an_answer_is_held_to_the_part_rather_than_to_the_emulator_recording(self) -> None:
        # Arrange
        rom, sym, trace = self.setUpFiles()
        trace.write_bytes(recorded_multiply())
        said: list[str] = []

        # Act
        code = cost.main(
            ["cost.py", str(rom), str(sym), str(trace), "1"],
            said.append,
            build=scripted(bytes(4)),
            refuses=lambda: None,
        )

        # Assert
        self.assertEqual((code, "1/1" in said[1]), (0, True))

    def test_an_answer_the_part_does_not_give_fails_even_when_the_recording_agrees(self) -> None:
        # Arrange
        rom, sym, trace = self.setUpFiles()
        trace.write_bytes(recorded_multiply(bytes(4)))
        said: list[str] = []

        # Act
        code = cost.main(
            ["cost.py", str(rom), str(sym), str(trace), "1"],
            said.append,
            build=scripted(RECORDED_ANSWER),
            refuses=lambda: None,
        )

        # Assert
        self.assertEqual((code, "0/1" in said[1]), (1, True))

    def test_with_no_part_to_ask_nothing_is_called_correct(self) -> None:
        # Arrange
        rom, sym, trace = self.setUpFiles()
        said: list[str] = []

        # Act
        code = cost.main(
            ["cost.py", str(rom), str(sym), str(trace), "1"],
            said.append,
            build=scripted(),
            refuses=lambda: "no microcode",
        )

        # Assert
        self.assertEqual((code, said), (2, ["  nothing to hold the answers to: no microcode"]))


class ExchangeTest(unittest.TestCase):
    def test_a_tile_answer_starts_after_the_byte_that_precedes_it(self) -> None:
        # Arrange
        one = ("tile", 0x01, (), bytes(32), bytes(2))

        # Act
        answer = cost.exchange(Scripted(bytes([0xEE, 0x01, 0x02])), one)

        # Assert
        self.assertEqual(answer, bytes([0x01, 0x02]))

    def test_the_byte_a_sync_leaves_behind_is_not_taken_for_the_next_answer(self) -> None:
        # Arrange
        found = [("sync", 0x0F, (), b"", b""), ("multiply", MULTIPLY, (), bytes(4), bytes(4))]

        # Act
        answers = cost.answered(Scripted(bytes([0xEE, 1, 2, 3, 4])), found, [0, 1])

        # Assert
        self.assertEqual(answers, {0: b"", 1: bytes([1, 2, 3, 4])})

    def test_the_recording_answers_with_what_the_cartridge_was_given(self) -> None:
        # Arrange
        found = [("multiply", MULTIPLY, (), bytes(4), RECORDED_ANSWER)]

        # Act
        answers = cost.recorded(found, [0])

        # Assert
        self.assertEqual(answers, {0: RECORDED_ANSWER})


class PartTest(unittest.TestCase):
    def test_the_part_built_is_the_dsp2(self) -> None:
        # Arrange
        asked: list[str] = []

        # Act
        cost.chip(build=asked.append)

        # Assert
        self.assertEqual(asked, ["dsp2"])

    def test_whether_the_part_can_run_is_a_reason_or_nothing(self) -> None:
        # Arrange
        expected_kinds = (type(None), str)

        # Act
        reason = cost.why_not()

        # Assert
        self.assertIsInstance(reason, expected_kinds)


script.entry(__name__, unittest.main)
