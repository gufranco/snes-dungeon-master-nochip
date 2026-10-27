import importlib.util
import tempfile
import unittest
from collections import namedtuple
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


Finished = namedtuple("Finished", "returncode stdout stderr")


def keeping(dump: Path) -> Any:
    written = dump.read_bytes()

    def _run(_args: Any) -> Any:
        dump.write_bytes(written)
        return Finished(0, "", "")

    return _run


def _capture(seen: list[Any], make: Any) -> Any:

    def _run(_build: Any, _skeleton: Any, batch: Any) -> Any:
        seen.append(batch)
        return b"script", make()

    return _run


def define(name: str, source: Path) -> int:
    for line in source.read_text().splitlines():
        head, _, tail = line.partition("=")
        if head.strip() != name:
            continue
        return int(tail.strip().split()[0].lstrip("$"), 16)
    raise AssertionError(f"{name} is not defined in {source.name}")


class CounterAddressTest(unittest.TestCase):
    def test_the_counter_base_matches_the_cartridge(self) -> None:
        self.assertEqual(replay.STATE, define("!R_STATE", ROOT / "asm" / "dsp2-replay.asm"))

    def test_the_counters_sit_above_the_chips_own_block(self) -> None:
        end = define("!STATE_END", ROOT / "asm" / "dsp2-state.asm")

        self.assertGreaterEqual(replay.STATE, end)

    def test_a_name_the_assembler_does_not_define_is_refused(self) -> None:
        with self.assertRaises(AssertionError):
            define("!NOT_A_DEFINE", ROOT / "asm" / "dsp2-replay.asm")


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

    def test_a_batch_the_emulator_could_not_run_ends_the_run(self) -> None:
        said: list[Any] = []

        def _fails(*_args: Any) -> Any:
            raise replay.EmulatorFailed("the container died")

        found = replay.walk(None, b"", [["one"]], _fails, said.append, int)

        self.assertIsNone(found)
        self.assertIn("did not run", said[-1])

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
                where,
                bytes(replay.IMAGE_BYTES),
                [(replay.KIND_WRITE, b"\x0f")],
                keeping(where / "replay-wram.bin"),
                lambda _d, _o: True,
            )

        self.assertTrue(script)
        self.assertTrue(found["finished"])

    def test_a_dump_that_arrives_late_is_waited_for(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "replay-wram.bin"
            ticks = iter([0.0, 1.0, 2.0, 3.0])

            found = replay.await_dump(
                dump, -1, lambda _s: dump.write_bytes(b"x"), lambda: next(ticks)
            )

        self.assertTrue(found)

    def test_a_dump_that_never_arrives_is_given_up_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "replay-wram.bin"
            ticks = iter([0.0, replay.DUMP_WAIT_SECONDS + 1.0])

            found = replay.await_dump(dump, -1, lambda _s: None, lambda: next(ticks))

        self.assertFalse(found)

    def test_a_dump_this_run_did_not_write_is_not_taken_for_one_it_did(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "replay-wram.bin"
            dump.write_bytes(b"x")
            ticks = iter([0.0, replay.DUMP_WAIT_SECONDS + 1.0])

            found = replay.await_dump(
                dump, dump.stat().st_mtime_ns, lambda _s: None, lambda: next(ticks)
            )

        self.assertFalse(found)

    def test_a_dump_already_newer_is_not_waited_for(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "replay-wram.bin"
            dump.write_bytes(b"x")
            waits: list[float] = []

            found = replay.await_dump(dump, -1, waits.append, lambda: 0.0)

        self.assertEqual((found, waits), (True, []))

    def test_a_non_zero_exit_from_the_emulator_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(replay.EmulatorFailed):
            replay.run_batch(
                Path(tmp),
                bytes(replay.IMAGE_BYTES),
                [(replay.KIND_WRITE, b"\x0f")],
                lambda _a: Finished(1, "", "the container died"),
            )

    def test_a_run_that_leaves_no_dump_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(replay.EmulatorFailed):
            replay.run_batch(
                Path(tmp),
                bytes(replay.IMAGE_BYTES),
                [(replay.KIND_WRITE, b"\x0f")],
                lambda _a: Finished(0, "", ""),
                lambda _d, _o: False,
            )

    def test_the_dump_from_an_earlier_batch_is_not_read_as_this_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            stale = bytearray(0x20000)
            stale[replay.STATE + replay.DONE] = replay.FINISHED
            (where / "replay-wram.bin").write_bytes(bytes(stale))

            with self.assertRaises(replay.EmulatorFailed):
                replay.run_batch(
                    where,
                    bytes(replay.IMAGE_BYTES),
                    [(replay.KIND_WRITE, b"\x0f")],
                    lambda _a: Finished(0, "", ""),
                    lambda _d, _o: False,
                )


class RealShellTest(unittest.TestCase):
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
