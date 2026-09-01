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


pace = load_module("pace", ROOT / "tools" / "pace.py")

Finished = namedtuple("Finished", "returncode stdout stderr")


def written(where: Path, hashes: list[str]) -> Path:
    where.write_text("".join(f"{n} {h} 50.0000\n" for n, h in enumerate(hashes)))
    return where


class ReadingTest(unittest.TestCase):
    """The per frame digests, in the order the run produced them."""

    def test_it_reads_one_digest_a_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            found = pace.digests(written(Path(tmp) / "h", ["aa", "bb", "cc"]))

        self.assertEqual(found, ["aa", "bb", "cc"])

    def test_a_line_it_cannot_read_is_left_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "h"
            where.write_text("0 aa 50.0\nrubbish\n1 bb 50.0\n")

            self.assertEqual(pace.digests(where), ["aa", "bb"])


class LagTest(unittest.TestCase):
    """How far behind the converted run is, frame by frame."""

    def test_two_identical_runs_never_fall_behind(self) -> None:
        self.assertEqual(pace.lags(["a", "b", "c"], ["a", "b", "c"]), [0, 0, 0])

    def test_a_run_one_frame_late_says_one(self) -> None:
        self.assertEqual(pace.lags(["a", "b", "c"], ["a", "a", "b", "c"]), [0, 1, 1])

    def test_a_frame_the_other_run_never_drew_is_marked_rather_than_dropped(self) -> None:
        self.assertEqual(pace.lags(["a", "z"], ["a", "a"]), [0, None])

    def test_one_frame_it_cannot_find_does_not_spend_the_rest_of_the_stream(self) -> None:
        self.assertEqual(pace.lags(["a", "z", "b"], ["a", "b"]), [0, None, 0])

    def test_a_picture_past_the_window_counts_as_never_drawn(self) -> None:
        self.assertEqual(pace.lags(["a", "b"], ["a", *["x"] * 200, "b"], window=5), [0, None])

    def test_the_search_never_looks_backwards(self) -> None:
        self.assertEqual(pace.lags(["a", "b", "a"], ["a", "b", "a"]), [0, 0, 0])


class VerdictTest(unittest.TestCase):
    """What the lags add up to."""

    def test_a_run_that_kept_up_says_so(self) -> None:
        found = pace.summary([0, 0, 0], 3)

        self.assertIn("never fell behind", found)

    def test_a_run_that_fell_behind_reports_the_worst(self) -> None:
        found = pace.summary([0, 1, 4, 2], 4)

        self.assertIn("worst 4", found)

    def test_it_reports_how_much_of_the_run_it_could_follow(self) -> None:
        found = pace.summary([0, 1], 10)

        self.assertIn("2 of 10", found)

    def test_frames_the_other_run_never_drew_are_counted_apart(self) -> None:
        found = pace.summary([0, None, 0], 3)

        self.assertIn("1 never drawn the same", found)

    def test_a_run_it_could_not_follow_at_all_says_that(self) -> None:
        self.assertIn("nothing", pace.summary([None, None], 10))


class CurveTest(unittest.TestCase):
    """The shape of the lag across the run."""

    def test_a_run_that_never_fell_behind_is_flat_at_nothing(self) -> None:
        found = pace.curve([0] * 8, steps=4)

        self.assertEqual([lag for _at, lag in found], [0, 0, 0, 0])

    def test_a_lag_that_grows_shows_as_growing(self) -> None:
        found = pace.curve([0, 0, 5, 5, 9, 9], steps=3)

        self.assertEqual([lag for _at, lag in found], [0, 5, 9])

    def test_each_point_says_which_frame_it_starts_at(self) -> None:
        found = pace.curve([0, 0, 5, 5], steps=2)

        self.assertEqual([at for at, _lag in found], [0, 2])

    def test_frames_that_never_matched_are_not_points_on_it(self) -> None:
        found = pace.curve([None, 3, None, 3], steps=2)

        self.assertEqual([at for at, _lag in found], [1, 3])

    def test_a_run_with_nothing_matched_has_no_curve(self) -> None:
        self.assertEqual(pace.curve([None, None]), [])


class CommandTest(unittest.TestCase):
    """The command line."""

    def test_a_missing_cartridge_is_reported_rather_than_run(self) -> None:
        said: list[str] = []

        code = pace.main(["pace.py", "/nonexistent.sfc", "/also-not.sfc"], said.append)

        self.assertEqual((code, "cannot find" in said[0]), (2, True))

    def test_it_asks_for_what_it_needs(self) -> None:
        said: list[str] = []

        code = pace.main(["pace.py"], said.append)

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def test_an_emulator_that_did_not_run_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            retail, converted = Path(tmp) / "a.sfc", Path(tmp) / "b.sfc"
            retail.write_bytes(b"\x00")
            converted.write_bytes(b"\x00")
            said: list[str] = []

            code = pace.main(
                ["pace.py", str(retail), str(converted), "3"],
                said.append,
                execute=lambda _a: Finished(1, "", "the container died"),
            )

        self.assertEqual((code, "did not run" in "\n".join(said)), (1, True))

    def test_a_pair_of_runs_is_compared_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            retail, converted = where / "a.sfc", where / "b.sfc"
            retail.write_bytes(b"\x00")
            converted.write_bytes(b"\x00")

            def _run(args: list[str]) -> Any:
                name = pace.HASHES_RETAIL if "a.sfc" in args else pace.HASHES_CONVERTED
                rows = ["aa", "bb", "cc"] if "a.sfc" in args else ["aa", "aa", "bb", "cc"]
                written(where / name, rows)
                return Finished(0, "", "")

            said: list[str] = []

            code = pace.main(
                ["pace.py", str(retail), str(converted), "3"], said.append, execute=_run
            )

        self.assertEqual((code, "worst 1" in "\n".join(said)), (0, True))


class RealShellTest(unittest.TestCase):
    """The path that actually shells out, run against a command that does nothing."""

    def test_it_runs_the_command_and_hands_back_what_it_returned(self) -> None:
        found = pace._shell_out(["true"])

        self.assertEqual(found.returncode, 0)


class InputTest(unittest.TestCase):
    """The input both cartridges are driven with, which the run writes for itself."""

    def test_the_same_script_is_there_before_either_starts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            retail, converted = where / "a.sfc", where / "b.sfc"
            retail.write_bytes(b"\x00")
            converted.write_bytes(b"\x00")
            present: list[bool] = []

            def _run(args: list[str]) -> Any:
                present.append((where / pace.SCRIPT).exists())
                name = pace.HASHES_RETAIL if "a.sfc" in args else pace.HASHES_CONVERTED
                written(where / name, ["aa"])
                return Finished(0, "", "")

            pace.main(
                ["pace.py", str(retail), str(converted), "3000"], lambda _l: None, execute=_run
            )

        self.assertEqual(present, [True, True])


class ShellingOutTest(unittest.TestCase):
    """The command that reaches the emulator."""

    def test_it_asks_for_the_digests(self) -> None:
        args = pace.run_command(Path("/w"), "dm.sfc", "h.txt", 100)

        self.assertIn("DMHASH=h.txt", args)

    def test_it_runs_without_network(self) -> None:
        args = pace.run_command(Path("/w"), "dm.sfc", "h.txt", 100)

        self.assertIn("--network=none", args)

    def test_a_relative_directory_is_resolved_before_it_is_mounted(self) -> None:
        args = pace.run_command(Path("build"), "dm.sfc", "h.txt", 100)

        self.assertTrue(args[args.index("-v") + 1].startswith("/"))


if __name__ == "__main__":
    unittest.main()
