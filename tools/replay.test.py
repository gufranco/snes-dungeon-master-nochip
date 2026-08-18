import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


replay = load_module("replay", ROOT / "tools" / "replay.py")


class RunTest(unittest.TestCase):
    def test_consecutive_writes_become_one_run(self):
        runs = list(replay.runs_from([(0, 1), (0, 2), (0, 3)]))

        self.assertEqual(runs, [(0, b"\x01\x02\x03")])

    def test_a_change_of_direction_starts_a_run(self):
        runs = list(replay.runs_from([(0, 1), (1, 2), (0, 3)]))

        self.assertEqual(runs, [(0, b"\x01"), (1, b"\x02"), (0, b"\x03")])

    def test_an_empty_stream_gives_no_runs(self):
        self.assertEqual(list(replay.runs_from([])), [])


class ScriptTest(unittest.TestCase):
    def test_a_write_run_becomes_a_feed(self):
        script = replay.script_for([(replay.KIND_WRITE, b"\x0f")])

        self.assertEqual(script[0], replay.FEED)
        self.assertEqual(script[1:3], (1).to_bytes(2, "little"))
        self.assertEqual(script[3], 0x0F)

    def test_a_read_run_carries_the_bytes_to_check_against(self):
        script = replay.script_for([(replay.KIND_READ, b"\xaa\xbb")])

        self.assertEqual(script[0], replay.CHECK)
        self.assertEqual(script[1:3], (2).to_bytes(2, "little"))
        self.assertEqual(script[3:5], b"\xaa\xbb")

    def test_the_script_ends_with_the_stop_marker(self):
        self.assertEqual(replay.script_for([])[-1], replay.END)

    def test_a_run_longer_than_a_count_is_split(self):
        script = replay.script_for([(replay.KIND_WRITE, b"\x11" * (replay.RUN_LIMIT + 5))])

        self.assertEqual(int.from_bytes(script[1:3], "little"), replay.RUN_LIMIT)

    def test_a_split_run_keeps_every_byte(self):
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
    def test_the_script_is_laid_out_in_the_upper_half_of_each_bank(self):
        image = replay.place_script(bytes(0x100000), b"\xaa" * 10, 0x02)

        self.assertEqual(image[0x10000:0x1000A], b"\xaa" * 10)

    def test_a_script_longer_than_a_bank_continues_in_the_next(self):
        script = bytes([1]) * 0x8000 + bytes([2]) * 16
        image = replay.place_script(bytes(0x100000), script, 0x02)

        self.assertEqual(image[0x10000], 1)
        self.assertEqual(image[0x18000], 2)

    def test_the_image_keeps_its_size(self):
        image = replay.place_script(bytes(0x100000), b"\xaa", 0x02)

        self.assertEqual(len(image), 0x100000)

    def test_a_script_that_does_not_fit_is_refused(self):
        with self.assertRaises(replay.ScriptTooLong):
            replay.place_script(bytes(0x20000), b"\xaa" * 0x10001, 0x02)

    def test_a_script_that_exactly_fills_the_room_is_accepted(self):
        image = replay.place_script(bytes(0x20000), b"\xaa" * 0x10000, 0x02)

        self.assertEqual(len(image), 0x20000)

    def test_the_capacity_counts_only_the_half_of_each_bank_that_exists(self):
        self.assertEqual(replay.capacity(0x100000, 0x02), (32 - 2) * 0x8000)

    def test_the_capacity_stops_where_work_RAM_takes_over(self):
        self.assertEqual(replay.capacity(0x400000, 0x02), (replay.WORK_RAM_BANK - 2) * 0x8000)

    def test_a_script_reaching_into_work_RAM_is_refused(self):
        room = replay.capacity(0x400000, 0x02)

        with self.assertRaises(replay.ScriptTooLong):
            replay.place_script(bytes(0x400000), b"\xaa" * (room + 1), 0x02)


class BatchTest(unittest.TestCase):
    def test_runs_are_grouped_until_the_room_is_used(self):
        runs = [(replay.KIND_WRITE, b"\x00" * 100) for _ in range(10)]

        batches = replay.batches_of(runs, 500)

        self.assertGreater(len(batches), 1)
        self.assertEqual(sum(len(batch) for batch in batches), 10)

    def test_a_batch_never_splits_a_run(self):
        runs = [(replay.KIND_WRITE, b"\x00" * 100), (replay.KIND_READ, b"\x01" * 100)]

        for batch in replay.batches_of(runs, 500):
            for _, payload in batch:
                self.assertEqual(len(payload), 100)

    def test_every_run_appears_exactly_once(self):
        runs = [(replay.KIND_WRITE, bytes([n])) for n in range(50)]

        flat = [run for batch in replay.batches_of(runs, 40) for run in batch]

        self.assertEqual(flat, runs)


class StatefulBatchTest(unittest.TestCase):
    def chip(self):
        dsp2 = load_module("dsp2", ROOT / "dsp2.py")
        return dsp2.Chip()

    def merge_runs(self, count):
        runs = []
        for _ in range(count):
            runs.append((replay.KIND_WRITE, bytes([0x05, 0x04]) + bytes(8)))
            runs.append((replay.KIND_READ, bytes(4)))
        return runs

    def test_a_batch_never_begins_with_a_read(self):
        batches = list(replay.stream_batches(self.merge_runs(40), 200, self.chip()))

        self.assertGreater(len(batches), 1)
        for batch in batches:
            self.assertEqual(batch[0][0], replay.KIND_WRITE)

    def test_a_later_batch_restores_the_transparent_colour(self):
        runs = [(replay.KIND_WRITE, bytes([0x03, 0x0A])), *self.merge_runs(40)]

        batches = list(replay.stream_batches(runs, 200, self.chip()))

        self.assertEqual(batches[1][0], (replay.KIND_WRITE, bytes([0x0F, 0x03, 0x0A])))

    def test_the_first_batch_carries_no_prelude(self):
        runs = self.merge_runs(40)

        batches = list(replay.stream_batches(runs, 200, self.chip()))

        self.assertEqual(batches[0][0], runs[0])

    def test_every_run_survives_exactly_once(self):
        runs = self.merge_runs(40)

        flat = [
            run
            for batch in replay.stream_batches(runs, 200, self.chip())
            for run in batch
            if run[1][:1] != b"\x0f"
        ]

        self.assertEqual(flat, runs)

    def test_every_batch_fits_the_room_it_was_given(self):
        for batch in replay.stream_batches(self.merge_runs(200), 300, self.chip()):
            self.assertLessEqual(len(replay.script_for(batch)), 300 + replay.MAX_OVERSHOOT)

    def test_a_command_is_never_split_across_batches(self):
        runs = self.merge_runs(40)

        for batch in replay.stream_batches(runs, 200, self.chip()):
            body = [run for run in batch if run[1][:1] != b"\x0f"]
            self.assertEqual(body[0][1][0], 0x05)


class ResultTest(unittest.TestCase):
    def test_counters_are_read_from_the_dump(self):
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

    def test_a_run_that_did_not_finish_says_so(self):
        self.assertFalse(replay.read_counters(bytes(0x20000))["finished"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
