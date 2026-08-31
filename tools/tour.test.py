import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "tour.py"


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("tour", MODULE_PATH)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tour = load_module()


def parse(text):
    steps = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        steps.append((int(parts[0]), tuple(parts[1:])))
    return steps


class DeterminismTest(unittest.TestCase):
    def test_the_same_seed_produces_the_same_script(self) -> None:
        first = tour.build(frames=4000, seed=99)
        second = tour.build(frames=4000, seed=99)

        self.assertEqual(first, second)

    def test_a_different_seed_produces_a_different_script(self) -> None:
        first = tour.build(frames=4000, seed=1)
        second = tour.build(frames=4000, seed=2)

        self.assertNotEqual(first, second)


class FormatTest(unittest.TestCase):
    def setUp(self) -> None:
        self.steps = parse(tour.build(frames=6000, seed=7))

    def test_every_line_carries_a_frame_number(self) -> None:
        self.assertTrue(self.steps)
        for frame, _ in self.steps:
            self.assertGreaterEqual(frame, 0)

    def test_frames_never_go_backwards(self) -> None:
        frames = [frame for frame, _ in self.steps]

        self.assertEqual(frames, sorted(frames))

    def test_no_frame_is_given_two_different_inputs(self) -> None:
        frames = [frame for frame, _ in self.steps]

        self.assertEqual(len(frames), len(set(frames)))

    def test_every_button_is_one_the_harness_knows(self) -> None:
        for _, buttons in self.steps:
            for button in buttons:
                self.assertIn(button, tour.BUTTONS)

    def test_nothing_is_scheduled_past_the_requested_length(self) -> None:
        for frame, _ in self.steps:
            self.assertLess(frame, 6000)


class ShapeTest(unittest.TestCase):
    def test_the_opening_presses_start_to_clear_the_introduction(self) -> None:
        steps = parse(tour.build(frames=6000, seed=3))

        opening = [buttons for frame, buttons in steps if frame < tour.INTRO_FRAMES]

        self.assertIn(("start",), opening)

    def test_the_body_interleaves_cursor_moves_with_clicks(self) -> None:
        steps = parse(tour.build(frames=12000, seed=3))

        body = [buttons for frame, buttons in steps if frame >= tour.INTRO_FRAMES]
        directions = {("up",), ("down",), ("left",), ("right",)}
        self.assertTrue(any(b in directions for b in body))
        self.assertTrue(any(b == ("a",) for b in body))

    def test_every_press_is_followed_by_a_release(self) -> None:
        steps = parse(tour.build(frames=8000, seed=5))

        releases = [buttons for _, buttons in steps if buttons == ()]

        self.assertGreater(len(releases), len(steps) // 3)

    def test_a_longer_tour_schedules_more_input(self) -> None:
        short = parse(tour.build(frames=6000, seed=4))
        long = parse(tour.build(frames=20000, seed=4))

        self.assertGreater(len(long), len(short))


class StreamTest(unittest.TestCase):
    def test_a_complaint_goes_to_the_error_stream_by_default(self) -> None:
        import io
        from contextlib import redirect_stderr

        caught = io.StringIO()
        with redirect_stderr(caught):
            tour._to_stderr("something went wrong")

        self.assertIn("something went wrong", caught.getvalue())

    def test_and_a_tour_goes_to_the_output_stream(self) -> None:
        import io
        from contextlib import redirect_stdout

        caught = io.StringIO()
        with redirect_stdout(caught):
            tour.main(["tour.py", "--frames", "600"])

        self.assertIn("start", caught.getvalue())

    def test_a_line_with_nothing_on_it_is_passed_over(self) -> None:
        self.assertEqual(parse("\n# only a comment\n"), [])


class EntryTest(unittest.TestCase):
    """The command line, which is how a tour is actually produced."""

    def test_a_run_with_no_arguments_writes_a_tour_to_the_output(self) -> None:
        said = []

        code = tour.main(["tour.py", "--frames", "600"], say=said.append)

        self.assertEqual(code, 0)
        self.assertTrue(said)

    def test_a_seed_is_taken_from_the_command_line(self) -> None:
        first = []
        second = []

        tour.main(["tour.py", "--frames", "4000", "--seed", "1"], say=first.append)
        tour.main(["tour.py", "--frames", "4000", "--seed", "2"], say=second.append)

        self.assertNotEqual(first, second)

    def test_an_out_path_is_written_rather_than_printed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp) / "tour.txt"
            said = []

            code = tour.main(["tour.py", "--frames", "600", "--out", str(where)], say=said.append)

            self.assertEqual(code, 0)
            self.assertTrue(where.read_text())
            self.assertIn("wrote", " ".join(said))

    def test_an_argument_nobody_recognises_is_refused_with_the_usage(self) -> None:
        complained = []

        code = tour.main(["tour.py", "--nonsense"], complain=complained.append)

        self.assertEqual(code, 2)
        self.assertIn("usage", complained[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
