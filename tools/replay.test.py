import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


replay = load_module("replay", ROOT / "tools" / "replay.py")


def _capture(seen: list[Any], make: Any) -> Any:
    """A stand-in for one batch run that keeps the batch it was handed."""

    def _run(_build: Any, _skeleton: Any, batch: Any) -> Any:
        seen.append(batch)
        return b"script", make()

    return _run


class RunTest(unittest.TestCase):
    def test_consecutive_writes_become_one_run(self) -> None:
        runs = list(replay.runs_from([(0, 1), (0, 2), (0, 3)]))

        self.assertEqual(runs, [(0, b"\x01\x02\x03")])

    def test_a_change_of_direction_starts_a_run(self) -> None:
        runs = list(replay.runs_from([(0, 1), (1, 2), (0, 3)]))

        self.assertEqual(runs, [(0, b"\x01"), (1, b"\x02"), (0, b"\x03")])

    def test_an_empty_stream_gives_no_runs(self) -> None:
        self.assertEqual(list(replay.runs_from([])), [])


class ScriptTest(unittest.TestCase):
    def test_a_write_run_becomes_a_feed(self) -> None:
        script = replay.script_for([(replay.KIND_WRITE, b"\x0f")])

        self.assertEqual(script[0], replay.FEED)
        self.assertEqual(script[1:3], (1).to_bytes(2, "little"))
        self.assertEqual(script[3], 0x0F)

    def test_a_read_run_carries_the_bytes_to_check_against(self) -> None:
        script = replay.script_for([(replay.KIND_READ, b"\xaa\xbb")])

        self.assertEqual(script[0], replay.CHECK)
        self.assertEqual(script[1:3], (2).to_bytes(2, "little"))
        self.assertEqual(script[3:5], b"\xaa\xbb")

    def test_the_script_ends_with_the_stop_marker(self) -> None:
        self.assertEqual(replay.script_for([])[-1], replay.END)

    def test_a_run_longer_than_a_count_is_split(self) -> None:
        script = replay.script_for([(replay.KIND_WRITE, b"\x11" * (replay.RUN_LIMIT + 5))])

        self.assertEqual(int.from_bytes(script[1:3], "little"), replay.RUN_LIMIT)

    def test_a_split_run_keeps_every_byte(self) -> None:
        payload = bytes(range(256)) * 300
        script = replay.script_for([(replay.KIND_WRITE, payload)])

        carried = bytearray()
        at = 0
        while script[at] != replay.END:
            count = int.from_bytes(script[at + 1 : at + 3], "little")
            carried += script[at + 3 : at + 3 + count]
            at += 3 + count

        self.assertEqual(bytes(carried), payload)


class LayoutTest(unittest.TestCase):
    def test_the_script_is_laid_out_in_the_upper_half_of_each_bank(self) -> None:
        image = replay.place_script(bytes(0x100000), b"\xaa" * 10, 0x02)

        self.assertEqual(image[0x10000:0x1000A], b"\xaa" * 10)

    def test_a_script_longer_than_a_bank_continues_in_the_next(self) -> None:
        script = bytes([1]) * 0x8000 + bytes([2]) * 16
        image = replay.place_script(bytes(0x100000), script, 0x02)

        self.assertEqual(image[0x10000], 1)
        self.assertEqual(image[0x18000], 2)

    def test_the_image_keeps_its_size(self) -> None:
        image = replay.place_script(bytes(0x100000), b"\xaa", 0x02)

        self.assertEqual(len(image), 0x100000)

    def test_a_script_that_does_not_fit_is_refused(self) -> None:
        with self.assertRaises(replay.ScriptTooLong):
            replay.place_script(bytes(0x20000), b"\xaa" * 0x10001, 0x02)

    def test_a_script_that_exactly_fills_the_room_is_accepted(self) -> None:
        image = replay.place_script(bytes(0x20000), b"\xaa" * 0x10000, 0x02)

        self.assertEqual(len(image), 0x20000)

    def test_the_capacity_counts_only_the_half_of_each_bank_that_exists(self) -> None:
        self.assertEqual(replay.capacity(0x100000, 0x02), (32 - 2) * 0x8000)

    def test_the_capacity_stops_where_work_RAM_takes_over(self) -> None:
        self.assertEqual(replay.capacity(0x400000, 0x02), (replay.WORK_RAM_BANK - 2) * 0x8000)

    def test_a_script_reaching_into_work_RAM_is_refused(self) -> None:
        room = replay.capacity(0x400000, 0x02)

        with self.assertRaises(replay.ScriptTooLong):
            replay.place_script(bytes(0x400000), b"\xaa" * (room + 1), 0x02)


class BatchTest(unittest.TestCase):
    def test_runs_are_grouped_until_the_room_is_used(self) -> None:
        runs = [(replay.KIND_WRITE, b"\x00" * 100) for _ in range(10)]

        batches = replay.batches_of(runs, 500)

        self.assertGreater(len(batches), 1)
        self.assertEqual(sum(len(batch) for batch in batches), 10)

    def test_a_batch_never_splits_a_run(self) -> None:
        runs = [(replay.KIND_WRITE, b"\x00" * 100), (replay.KIND_READ, b"\x01" * 100)]

        for batch in replay.batches_of(runs, 500):
            for _, payload in batch:
                self.assertEqual(len(payload), 100)

    def test_every_run_appears_exactly_once(self) -> None:
        runs = [(replay.KIND_WRITE, bytes([n])) for n in range(50)]

        flat = [run for batch in replay.batches_of(runs, 40) for run in batch]

        self.assertEqual(flat, runs)


class StatefulBatchTest(unittest.TestCase):
    """Where a batch may break, which is a question about shape rather than values.

    Nothing here asks a part what it computes. It asks the stream where a fresh
    cartridge could take over, which is the one thing a batch boundary has to get
    right, and that is tracked from the bytes themselves.
    """

    def chip(self) -> Any:
        return replay.protocol.Shape()

    def merge_runs(self, count: Any) -> Any:
        runs: list[Any] = []
        for _ in range(count):
            runs.append((replay.KIND_WRITE, bytes([0x05, 0x04]) + bytes(8)))
            runs.append((replay.KIND_READ, bytes(4)))
        return runs

    def test_a_batch_never_begins_with_a_read(self) -> None:
        batches = list(replay.stream_batches(self.merge_runs(40), 200, self.chip()))

        self.assertGreater(len(batches), 1)
        for batch in batches:
            self.assertEqual(batch[0][0], replay.KIND_WRITE)

    def test_a_later_batch_restores_the_transparent_colour(self) -> None:
        runs = [(replay.KIND_WRITE, bytes([0x03, 0x0A])), *self.merge_runs(40)]

        batches = list(replay.stream_batches(runs, 200, self.chip()))

        self.assertEqual(batches[1][0], (replay.KIND_WRITE, bytes([0x0F, 0x03, 0x0A])))

    def test_the_first_batch_carries_no_prelude(self) -> None:
        runs = self.merge_runs(40)

        batches = list(replay.stream_batches(runs, 200, self.chip()))

        self.assertEqual(batches[0][0], runs[0])

    def test_every_run_survives_exactly_once(self) -> None:
        runs = self.merge_runs(40)

        flat = [
            run
            for batch in replay.stream_batches(runs, 200, self.chip())
            for run in batch
            if run[1][:1] != b"\x0f"
        ]

        self.assertEqual(flat, runs)

    def test_every_batch_fits_the_room_it_was_given(self) -> None:
        for batch in replay.stream_batches(self.merge_runs(200), 300, self.chip()):
            self.assertLessEqual(len(replay.script_for(batch)), 300 + replay.MAX_OVERSHOOT)

    def test_a_command_is_never_split_across_batches(self) -> None:
        runs = self.merge_runs(40)

        for batch in replay.stream_batches(runs, 200, self.chip()):
            body = [run for run in batch if run[1][:1] != b"\x0f"]
            self.assertEqual(body[0][1][0], 0x05)


class ResultTest(unittest.TestCase):
    def test_counters_are_read_from_the_dump(self) -> None:
        dump = bytearray(0x20000)
        at = replay.STATE
        dump[at + replay.DONE] = 0xA5
        dump[at + replay.TRANSACTIONS : at + replay.TRANSACTIONS + 4] = (7).to_bytes(4, "little")
        dump[at + replay.COMPARED : at + replay.COMPARED + 4] = (900).to_bytes(4, "little")
        dump[at + replay.WRONG : at + replay.WRONG + 4] = (2).to_bytes(4, "little")
        dump[at + replay.FIRST : at + replay.FIRST + 4] = (11).to_bytes(4, "little")
        dump[at + replay.EXPECTED] = 0x12
        dump[at + replay.RETURNED] = 0x34

        found = replay.read_counters(bytes(dump))

        self.assertTrue(found["finished"])
        self.assertEqual(found["transactions"], 7)
        self.assertEqual(found["compared"], 900)
        self.assertEqual(found["wrong"], 2)
        self.assertEqual(found["first"], 11)
        self.assertEqual(found["expected"], 0x12)
        self.assertEqual(found["returned"], 0x34)

    def test_a_run_that_did_not_finish_says_so(self) -> None:
        self.assertFalse(replay.read_counters(bytes(0x20000))["finished"])


def a_batch(
    finished: Any = True,
    wrong: Any = 0,
    compared: Any = 4,
    transactions: Any = 2,
) -> Any:
    return {
        "finished": finished,
        "wrong": wrong,
        "compared": compared,
        "transactions": transactions,
        "first": 0,
        "expected": 0x11,
        "returned": 0x22,
    }


class WalkTest(unittest.TestCase):
    def test_a_run_where_every_batch_finishes_reports_what_it_checked(self) -> None:
        found = replay.walk(
            None, b"", [["one"], ["two"]], lambda *_: (b"s", a_batch()), lambda _l: None, int
        )

        self.assertEqual(found[:3], (4, 8, 0))

    def test_a_batch_that_does_not_finish_ends_the_run(self) -> None:
        said: list[Any] = []

        found = replay.walk(
            None, b"", [["one"]], lambda *_: (b"s", a_batch(finished=False)), said.append, int
        )

        self.assertIsNone(found)
        self.assertIn("did not finish", said[-1])

    def test_a_batch_with_disagreements_is_kept_for_the_summary(self) -> None:
        found = replay.walk(
            None, b"", [["one"]], lambda *_: (b"s", a_batch(wrong=2)), lambda _l: None, int
        )

        self.assertEqual(found[2], 2)
        self.assertEqual(len(found[3]), 1)


class SummaryTest(unittest.TestCase):
    def test_it_says_how_much_went_each_way(self) -> None:
        lines = "\n".join(replay.summary_lines(10, 4, 1, 4, 0, []))

        self.assertIn("written 10", lines)
        self.assertIn("returned 4", lines)

    def test_a_disagreement_names_what_both_sides_had(self) -> None:
        lines = "\n".join(replay.summary_lines(1, 1, 1, 1, 1, [(0, a_batch(wrong=1))]))

        self.assertIn("cartridge $11", lines)
        self.assertIn("routines $22", lines)

    def test_no_more_than_a_handful_of_batches_are_listed(self) -> None:
        failures = [(number, a_batch(wrong=1)) for number in range(20)]

        lines = replay.summary_lines(0, 0, 0, 0, 20, failures)

        self.assertEqual(sum(1 for line in lines if "first at byte" in line), 5)


class EntryTest(unittest.TestCase):
    def _record(self, kind: Any, byte: Any) -> Any:
        return type("Record", (), {"kind": kind, "byte": byte})()

    def test_no_argument_at_all_is_refused_with_the_usage(self) -> None:
        said: list[Any] = []

        self.assertEqual(replay.main([], say=said.append), 2)
        self.assertIn("usage", said[0])

    def test_a_trace_that_is_not_there_is_a_skip_rather_than_a_failure(self) -> None:
        said: list[Any] = []

        code = replay.main(["/nowhere/at/all.bin"], say=said.append)

        self.assertEqual(code, 0)
        self.assertIn("no trace", said[0])

    def test_a_run_where_everything_agrees_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "trace.bin"
            where.write_bytes(b"\x00")
            reading = [self._record(replay.KIND_WRITE, 0x0F)]

            code = replay.main(
                [str(where)],
                assemble=lambda *_: b"skeleton",
                run_batch=lambda *_: (b"script", a_batch()),
                records=lambda _path: reading,
                say=lambda _l: None,
                clock=int,
            )

        self.assertEqual(code, 0)

    def test_a_run_with_a_disagreement_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "trace.bin"
            where.write_bytes(b"\x00")

            code = replay.main(
                [str(where)],
                assemble=lambda *_: b"skeleton",
                run_batch=lambda *_: (b"script", a_batch(wrong=1)),
                records=lambda _path: [self._record(replay.KIND_WRITE, 0x0F)],
                say=lambda _l: None,
                clock=int,
            )

        self.assertEqual(code, 1)

    def test_a_batch_that_does_not_finish_fails_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "trace.bin"
            where.write_bytes(b"\x00")

            code = replay.main(
                [str(where)],
                assemble=lambda *_: b"skeleton",
                run_batch=lambda *_: (b"script", a_batch(finished=False)),
                records=lambda _path: [self._record(replay.KIND_WRITE, 0x0F)],
                say=lambda _l: None,
                clock=int,
            )

        self.assertEqual(code, 1)

    def test_what_the_chip_returned_is_counted_as_well_as_what_was_written(self) -> None:
        said: list[Any] = []

        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "trace.bin"
            where.write_bytes(b"\x00")
            reading = [
                self._record(replay.KIND_WRITE, 0x09),
                self._record(replay.KIND_READ, 0x11),
            ]

            replay.main(
                [str(where)],
                assemble=lambda *_: b"skeleton",
                run_batch=lambda *_: (b"script", a_batch()),
                records=lambda _path: reading,
                say=said.append,
                clock=int,
            )

        self.assertIn("the chip returned 1", " ".join(said))

    def test_a_record_limit_stops_the_stream_where_it_says(self) -> None:
        seen: list[Any] = []

        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "trace.bin"
            where.write_bytes(b"\x00")
            reading = [self._record(replay.KIND_WRITE, 0x0F) for _ in range(10)]

            replay.main(
                [str(where), "3"],
                assemble=lambda *_: b"skeleton",
                run_batch=_capture(seen, a_batch),
                records=lambda _path: reading,
                say=lambda _l: None,
                clock=int,
            )

        self.assertEqual(sum(len(payload) for _kind, payload in seen[0]), 3)


class ShellingOutTest(unittest.TestCase):
    """What the two Docker commands are, checked without Docker."""

    def test_assembling_names_the_pinned_assembler_and_the_source(self) -> None:
        found = replay.assemble_command(Path("/root"), Path("/build"))

        self.assertIn(replay.ASSEMBLER, found)
        self.assertIn("dsp2-replay.asm /out/replay.sfc", " ".join(found))

    def test_running_names_the_pinned_emulator_and_where_to_stop(self) -> None:
        found = replay.run_command(Path("/build"))

        self.assertIn(replay.EMULATOR, found)
        self.assertIn(f"DMSTOP={replay.STATE + replay.DONE:X}:{replay.FINISHED:X}", found)

    def test_an_assembler_that_fails_stops_the_run_with_what_it_said(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            failed = type("Done", (), {"returncode": 1, "stderr": "asar said no", "stdout": ""})

            with self.assertRaises(SystemExit) as raised:
                replay.assemble(Path("/root"), Path(tmp), execute=lambda _args: failed)

        self.assertIn("asar said no", str(raised.exception))

    def test_an_assembler_that_succeeds_hands_back_the_image_it_wrote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            done = type("Done", (), {"returncode": 0, "stderr": "", "stdout": ""})

            found = replay.assemble(Path("/root"), Path(tmp), execute=lambda _args: done)

        self.assertEqual(len(found), replay.IMAGE_BYTES)

    def test_a_batch_writes_the_script_into_the_cartridge_and_reads_the_counters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            dump = bytearray(0x20000)
            dump[replay.STATE + replay.DONE] = replay.FINISHED
            (where / "replay-wram.bin").write_bytes(bytes(dump))

            script, found = replay.run_batch(
                where, bytes(replay.IMAGE_BYTES), [(replay.KIND_WRITE, b"\x0f")], lambda _a: None
            )

        self.assertTrue(script)
        self.assertTrue(found["finished"])


class RealShellTest(unittest.TestCase):
    """The path that actually shells out, run against a command that does nothing."""

    def test_it_runs_the_command_and_hands_back_what_it_returned(self) -> None:
        found = replay._shell_out(["true"])

        self.assertEqual(found.returncode, 0)


class LoadingTest(unittest.TestCase):
    def test_the_trace_reader_it_loads_is_the_one_beside_this_project(self) -> None:
        found = replay.load_dsptrace(ROOT)

        self.assertTrue(hasattr(found, "records"))


class BatchEdgeTest(unittest.TestCase):
    def test_a_stream_with_nothing_in_it_produces_no_batches(self) -> None:
        self.assertEqual(list(replay.stream_batches([], 100)), [])

    def test_and_grouping_nothing_produces_nothing_either(self) -> None:
        self.assertEqual(replay.batches_of([], 100), [])

    def test_a_run_larger_than_the_room_still_gets_a_batch_of_its_own(self) -> None:
        found = replay.batches_of([(replay.KIND_WRITE, bytes(500))], 100)

        self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
