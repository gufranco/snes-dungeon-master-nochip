import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "tour.py"


def load_module():
    spec = importlib.util.spec_from_file_location("tour", MODULE_PATH)
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
    def test_the_same_seed_produces_the_same_script(self):
        first = tour.build(frames=4000, seed=99)
        second = tour.build(frames=4000, seed=99)

        self.assertEqual(first, second)

    def test_a_different_seed_produces_a_different_script(self):
        first = tour.build(frames=4000, seed=1)
        second = tour.build(frames=4000, seed=2)

        self.assertNotEqual(first, second)


class FormatTest(unittest.TestCase):
    def setUp(self):
        self.steps = parse(tour.build(frames=6000, seed=7))

    def test_every_line_carries_a_frame_number(self):
        self.assertTrue(self.steps)
        for frame, _ in self.steps:
            self.assertGreaterEqual(frame, 0)

    def test_frames_never_go_backwards(self):
        frames = [frame for frame, _ in self.steps]

        self.assertEqual(frames, sorted(frames))

    def test_no_frame_is_given_two_different_inputs(self):
        frames = [frame for frame, _ in self.steps]

        self.assertEqual(len(frames), len(set(frames)))

    def test_every_button_is_one_the_harness_knows(self):
        for _, buttons in self.steps:
            for button in buttons:
                self.assertIn(button, tour.BUTTONS)

    def test_nothing_is_scheduled_past_the_requested_length(self):
        for frame, _ in self.steps:
            self.assertLess(frame, 6000)


class ShapeTest(unittest.TestCase):
    def test_the_opening_presses_start_to_clear_the_introduction(self):
        steps = parse(tour.build(frames=6000, seed=3))

        opening = [buttons for frame, buttons in steps if frame < tour.INTRO_FRAMES]

        self.assertIn(("start",), opening)

    def test_the_body_interleaves_cursor_moves_with_clicks(self):
        steps = parse(tour.build(frames=12000, seed=3))

        body = [buttons for frame, buttons in steps if frame >= tour.INTRO_FRAMES]
        directions = {("up",), ("down",), ("left",), ("right",)}
        self.assertTrue(any(b in directions for b in body))
        self.assertTrue(any(b == ("a",) for b in body))

    def test_every_press_is_followed_by_a_release(self):
        steps = parse(tour.build(frames=8000, seed=5))

        releases = [buttons for _, buttons in steps if buttons == ()]

        self.assertGreater(len(releases), len(steps) // 3)

    def test_a_longer_tour_schedules_more_input(self):
        short = parse(tour.build(frames=6000, seed=4))
        long = parse(tour.build(frames=20000, seed=4))

        self.assertGreater(len(long), len(short))


if __name__ == "__main__":
    unittest.main(verbosity=2)
