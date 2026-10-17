import importlib.util
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import dsptrace  # noqa: E402


def load_module(name: str, where: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, where / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


frame_cost = load_module("frame_cost", ROOT / "tools")

TRANSPARENT = 0x03
SYNC = 0x0F
MOVER = 0x040087
ROM_SITE = 0x9CE202


def write(byte: int, frame: int, pc: int = ROM_SITE) -> Any:
    return dsptrace.Record(frame, pc, 0, 0, dsptrace.KIND_WRITE, byte, 0, 0, None, None)


def transparent(frame: int, pc: int) -> list[Any]:
    return [write(TRANSPARENT, frame), write(0x05, frame, pc)]


def packed(one: Any) -> bytes:
    return dsptrace.RECORD.pack(
        one.frame, one.pc, one.x, one.y, one.kind, one.byte, bytes(8), 0, 0, bytes(4)
    )


def a_tally(**changes: Any) -> Any:
    fields = {"frames": 10, "calls": Counter(), "retail": Counter(), **changes}
    return frame_cost.Tally(**fields)


class MoverTest(unittest.TestCase):
    def test_a_transfer_run_from_a_block_mover_in_work_ram_is_dispatched(self) -> None:
        # Arrange
        one = write(0x00, 0, MOVER)

        # Act
        found = frame_cost.through_mover(one)

        # Assert
        self.assertTrue(found)

    def test_a_transfer_run_from_the_cartridge_is_direct(self) -> None:
        # Arrange
        one = write(0x00, 0, ROM_SITE)

        # Act
        found = frame_cost.through_mover(one)

        # Assert
        self.assertFalse(found)

    def test_the_byte_past_the_last_mover_is_not_one(self) -> None:
        # Arrange
        one = write(0x00, 0, 0x000090)

        # Act
        found = frame_cost.through_mover(one)

        # Assert
        self.assertFalse(found)

    def test_the_same_offset_in_a_bank_that_does_not_mirror_work_ram_is_not_a_mover(
        self,
    ) -> None:
        # Arrange
        one = write(0x00, 0, 0x400087)

        # Act
        found = frame_cost.through_mover(one)

        # Assert
        self.assertFalse(found)

    def test_a_mover_reached_through_the_fast_mirror_is_dispatched_too(self) -> None:
        # Arrange
        one = write(0x00, 0, 0x84008B)

        # Act
        found = frame_cost.through_mover(one)

        # Assert
        self.assertTrue(found)


class TallyTest(unittest.TestCase):
    def test_each_exchange_is_counted_under_the_way_it_arrived(self) -> None:
        # Arrange
        stream = [*transparent(700, MOVER), *transparent(701, ROM_SITE), *transparent(702, MOVER)]

        # Act
        found = frame_cost.tally(stream, 600, lambda *_a: 0)

        # Assert
        self.assertEqual(
            found.calls, Counter({("transparent", True): 2, ("transparent", False): 1})
        )

    def test_the_frames_counted_run_from_the_first_exchange_to_the_last(self) -> None:
        # Arrange
        stream = [write(SYNC, 700), write(SYNC, 709)]

        # Act
        found = frame_cost.tally(stream, 600, lambda *_a: 0)

        # Assert
        self.assertEqual(found.frames, 10)

    def test_an_exchange_before_the_settled_frame_is_left_out(self) -> None:
        # Arrange
        stream = [write(SYNC, 100), write(SYNC, 700)]

        # Act
        found = frame_cost.tally(stream, 600, lambda *_a: 0)

        # Assert
        self.assertEqual((found.calls, found.frames), (Counter({("sync", False): 1}), 1))

    def test_an_exchange_the_recording_cut_short_is_left_out(self) -> None:
        # Arrange
        stream = [write(SYNC, 700), write(TRANSPARENT, 701)]

        # Act
        found = frame_cost.tally(stream, 600, lambda *_a: 0)

        # Assert
        self.assertEqual(found.calls, Counter({("sync", False): 1}))

    def test_the_retail_price_of_every_exchange_is_summed_by_command(self) -> None:
        # Arrange
        stream = [*transparent(700, ROM_SITE), *transparent(701, MOVER)]

        # Act
        found = frame_cost.tally(stream, 600, lambda *_a: 12)

        # Assert
        self.assertEqual(found.retail, Counter({"transparent": 24}))

    def test_a_recording_with_nothing_after_the_settled_frame_spans_no_frames(self) -> None:
        # Arrange
        stream = [write(SYNC, 100)]

        # Act
        found = frame_cost.tally(stream, 600, lambda *_a: 0)

        # Assert
        self.assertEqual(found.frames, 0)


class CombinedTest(unittest.TestCase):
    def test_tours_add_their_frames_calls_and_retail_cycles(self) -> None:
        # Arrange
        first = a_tally(frames=10, calls=Counter({("tile", True): 3}), retail=Counter(tile=30))
        second = a_tally(frames=5, calls=Counter({("tile", True): 1}), retail=Counter(tile=7))

        # Act
        found = frame_cost.combined([first, second])

        # Assert
        self.assertEqual(
            (found.frames, found.calls, found.retail),
            (15, Counter({("tile", True): 4}), Counter(tile=37)),
        )


class RowsTest(unittest.TestCase):
    def test_a_command_is_priced_by_the_path_each_call_took(self) -> None:
        # Arrange
        found = a_tally(
            frames=10,
            calls=Counter({("tile", False): 4, ("tile", True): 6}),
            retail=Counter(tile=450),
        )

        # Act
        rows = frame_cost.rows(found, {"tile": (100.0, 200.0)})

        # Assert
        self.assertEqual(rows, [("tile", 10, 0.6, 160.0, 45.0)])

    def test_a_command_with_no_price_costs_nothing_on_our_side(self) -> None:
        # Arrange
        found = a_tally(frames=2, calls=Counter({("sync", False): 2}), retail=Counter(sync=10))

        # Act
        rows = frame_cost.rows(found, {})

        # Assert
        self.assertEqual(rows, [("sync", 2, 0.0, 0.0, 5.0)])


class ReportTest(unittest.TestCase):
    def test_a_recording_with_no_frames_says_so(self) -> None:
        # Arrange
        found = a_tally(frames=0)

        # Act
        lines = frame_cost.report(found, {})

        # Assert
        self.assertEqual(lines, ["  no complete exchange was recorded after the settled frame"])

    def test_the_last_line_is_the_cost_of_a_frame_on_both_sides(self) -> None:
        # Arrange
        found = a_tally(
            frames=10,
            calls=Counter({("tile", False): 10, ("merge", True): 20}),
            retail=Counter(tile=300, merge=500),
        )

        # Act
        lines = frame_cost.report(found, {"tile": (100.0, 0.0), "merge": (0.0, 50.0)})

        # Assert
        self.assertEqual(lines[-1].split(), ["a", "frame", "200", "80"])

    def test_every_command_gets_a_row_with_its_dispatched_share(self) -> None:
        # Arrange
        found = a_tally(frames=1, calls=Counter({("tile", False): 1, ("tile", True): 3}))

        # Act
        lines = frame_cost.report(found, {"tile": (1.0, 1.0)})

        # Assert
        self.assertEqual(lines[2].split(), ["tile", "4", "75%", "4", "0"])


class MeansTest(unittest.TestCase):
    def test_each_command_is_priced_at_the_mean_of_its_samples(self) -> None:
        # Arrange
        joined = {"tile": [(100, 110, 50, True), (200, 230, 50, True)]}

        # Act
        prices = frame_cost.means(joined)

        # Assert
        self.assertEqual(prices, {"tile": (150.0, 170.0)})


class LoadTest(unittest.TestCase):
    def test_the_cost_harness_is_the_one_beside_this_tool(self) -> None:
        # Arrange
        expected = ROOT / "tools" / "cost.py"

        # Act
        cost = frame_cost.load_cost()

        # Assert
        self.assertEqual(Path(cost.__file__), expected)


class FakeCost:
    SAMPLED = ("tile",)
    SETTLED_FRAME = 600

    def __init__(self) -> None:
        self.swept: list[bool] = []

    def symbols(self, text: str) -> dict[str, int]:
        return {"read": len(text)}

    def sweep(
        self, rom: bytes, names: Any, trace: Any, wanted: int, *_a: Any, dispatched: bool
    ) -> Any:
        self.swept.append(dispatched)
        return {"tile": [(300 if dispatched else 200, 90, True)]}

    def joined(self, direct: Any, dispatched: Any) -> Any:
        return {"tile": [(direct["tile"][0][0], dispatched["tile"][0][0], 90, True)]}

    def retail_cost(self, *_a: Any) -> int:
        return 7


class PricedTest(unittest.TestCase):
    def test_a_command_is_priced_on_both_paths(self) -> None:
        # Arrange
        where = Path(tempfile.mkdtemp())
        image = where / "dm-sym.sfc"
        image.write_bytes(bytes(16))
        image.with_suffix(".sym").write_text("[labels]\n")

        # Act
        prices = frame_cost.priced(FakeCost(), image, where / "trace.bin", 60)

        # Assert
        self.assertEqual(prices, {"tile": (200.0, 300.0)})


class MainTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.where = Path(tempfile.mkdtemp())
        self.image = self.where / "dm-sym.sfc"
        self.image.write_bytes(bytes(16))
        self.image.with_suffix(".sym").write_text("[labels]\n")

    def trace(self, records: list[Any]) -> Path:
        path = self.where / "trace.bin"
        path.write_bytes(b"".join(packed(one) for one in records))
        return path

    def test_a_missing_image_or_trace_is_named_and_refused(self) -> None:
        # Arrange
        said: list[str] = []

        # Act
        code = frame_cost.main(
            ["frame_cost.py", str(self.where / "absent.sfc")], say=said.append, load=FakeCost
        )

        # Assert
        self.assertEqual((code, "absent.sfc" in said[0]), (2, True))

    def test_a_recording_is_priced_per_frame(self) -> None:
        # Arrange
        trace = self.trace([*transparent(700, MOVER), *transparent(701, ROM_SITE)])
        said: list[str] = []

        # Act
        code = frame_cost.main(
            ["frame_cost.py", str(self.image), str(trace)],
            say=said.append,
            load=FakeCost,
            price=lambda *_a: {"transparent": (10.0, 30.0)},
        )

        # Assert
        self.assertEqual((code, said[-1].split()), (0, ["a", "frame", "20", "7"]))

    def test_a_recording_with_nothing_after_the_settled_frame_fails(self) -> None:
        # Arrange
        trace = self.trace([write(SYNC, 100)])
        said: list[str] = []

        # Act
        code = frame_cost.main(
            ["frame_cost.py", str(self.image), str(trace)],
            say=said.append,
            load=FakeCost,
            price=lambda *_a: {},
        )

        # Assert
        self.assertEqual(code, 1)

    def test_with_no_arguments_it_reads_the_image_and_the_three_tours_of_the_build(self) -> None:
        # Arrange
        said: list[str] = []
        self.addCleanup(setattr, frame_cost, "ROOT", frame_cost.ROOT)
        self.addCleanup(setattr, frame_cost, "TRACES", frame_cost.TRACES)
        frame_cost.ROOT = self.where
        frame_cost.TRACES = (self.where / "build" / "trace-s1.bin",)

        # Act
        code = frame_cost.main(["frame_cost.py"], say=said.append, load=FakeCost)

        # Assert
        self.assertEqual((code, "trace-s1.bin" in said[0]), (2, True))


if __name__ == "__main__":
    unittest.main()
