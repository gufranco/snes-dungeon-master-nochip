import importlib.util
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


protocol = load_module("protocol", ROOT / "tools" / "protocol.py")


def feed(shape: Any, *values: int) -> Any:
    for value in values:
        shape.wrote(value)
    return shape


class BoundaryTest(unittest.TestCase):
    def test_a_fresh_stream_is_waiting_for_a_command(self) -> None:
        self.assertTrue(protocol.Shape().at_boundary)

    def test_a_command_that_wants_bytes_leaves_the_stream_mid_command(self) -> None:
        self.assertFalse(feed(protocol.Shape(), protocol.MULTIPLY).at_boundary)

    def test_and_the_stream_is_back_at_a_boundary_once_it_has_them(self) -> None:
        shape = feed(protocol.Shape(), protocol.MULTIPLY, 2, 0, 3, 0)

        self.assertFalse(shape.at_boundary)
        self.assertEqual(shape.produced, 4)

    def test_a_sync_takes_nothing_and_leaves_the_stream_where_it_was(self) -> None:
        shape = feed(protocol.Shape(), protocol.SYNC)

        self.assertTrue(shape.at_boundary)
        self.assertEqual(shape.produced, 0)

    def test_a_byte_the_part_does_not_recognise_is_treated_the_same_way(self) -> None:
        shape = feed(protocol.Shape(), 0x42)

        self.assertTrue(shape.at_boundary)
        self.assertEqual(shape.produced, 0)


class ExpectingTest(unittest.TestCase):
    def test_a_fresh_stream_expects_a_command_rather_than_data(self) -> None:
        self.assertFalse(protocol.Shape().expecting_input)

    def test_a_command_mid_flight_is_still_expecting_its_data(self) -> None:
        self.assertTrue(feed(protocol.Shape(), protocol.TILE).expecting_input)

    def test_and_stops_expecting_once_it_has_it(self) -> None:
        self.assertFalse(feed(protocol.Shape(), protocol.TILE, *range(32)).expecting_input)


class OutputTest(unittest.TestCase):
    def test_a_tile_conversion_takes_thirty_two_bytes_and_gives_thirty_two_back(self) -> None:
        shape = feed(protocol.Shape(), protocol.TILE, *range(32))

        self.assertEqual(shape.produced, 32)

    def test_a_multiply_takes_four_and_gives_four(self) -> None:
        self.assertEqual(feed(protocol.Shape(), protocol.MULTIPLY, 1, 0, 2, 0).produced, 4)

    def test_a_transparent_colour_gives_nothing_back(self) -> None:
        self.assertEqual(feed(protocol.Shape(), protocol.TRANSPARENT, 0x0A).produced, 0)

    def test_a_merge_takes_twice_its_length_and_gives_its_length_back(self) -> None:
        shape = feed(protocol.Shape(), protocol.MERGE, 4, *range(8))

        self.assertEqual(shape.produced, 4)

    def test_a_mirror_takes_its_length_and_gives_its_length_back(self) -> None:
        shape = feed(protocol.Shape(), protocol.MIRROR, 4, *range(4))

        self.assertEqual(shape.produced, 4)

    def test_a_scale_gives_back_the_second_of_its_two_lengths(self) -> None:
        shape = feed(protocol.Shape(), protocol.SCALE, 4, 6, *range(2))

        self.assertEqual(shape.produced, 6)

    def test_a_merge_of_nothing_produces_nothing_and_waits_for_the_next_command(self) -> None:
        shape = feed(protocol.Shape(), protocol.MERGE, 0)

        self.assertTrue(shape.at_boundary)


class ReadingTest(unittest.TestCase):
    def test_reading_a_result_spends_it(self) -> None:
        shape = feed(protocol.Shape(), protocol.MULTIPLY, 1, 0, 2, 0)

        for _ in range(4):
            shape.was_read()

        self.assertEqual(shape.produced, 0)

    def test_a_result_read_only_in_part_still_has_the_rest(self) -> None:
        shape = feed(protocol.Shape(), protocol.MULTIPLY, 1, 0, 2, 0)

        shape.was_read()

        self.assertEqual(shape.produced, 3)

    def test_reading_when_there_is_nothing_to_read_is_not_an_error(self) -> None:
        shape = protocol.Shape()

        shape.was_read()

        self.assertEqual(shape.produced, 0)

    def test_a_stream_is_only_at_a_boundary_once_the_result_is_spent(self) -> None:
        shape = feed(protocol.Shape(), protocol.MULTIPLY, 1, 0, 2, 0)

        self.assertFalse(shape.at_boundary)
        for _ in range(4):
            shape.was_read()
        self.assertTrue(shape.at_boundary)


class TransparentTest(unittest.TestCase):
    """The one value the driver has to remember, because a batch boundary loses it."""

    def test_a_fresh_stream_has_not_been_told_a_colour(self) -> None:
        self.assertIsNone(protocol.Shape().transparent)

    def test_the_colour_a_command_set_is_remembered(self) -> None:
        self.assertEqual(feed(protocol.Shape(), protocol.TRANSPARENT, 0x0A).transparent, 0x0A)

    def test_and_the_last_one_wins(self) -> None:
        shape = feed(protocol.Shape(), protocol.TRANSPARENT, 0x0A, protocol.TRANSPARENT, 0x0C)

        self.assertEqual(shape.transparent, 0x0C)


class ArmingTest(unittest.TestCase):
    """That a length given once is used by the next appearance of its command."""

    def test_a_merge_length_given_with_no_payload_arms_the_next_merge(self) -> None:
        shape = feed(protocol.Shape(), protocol.MERGE, 0)

        feed(shape, protocol.MERGE)

        self.assertEqual(shape.produced, 0)

    def test_a_second_merge_after_a_length_runs_with_that_length(self) -> None:
        shape = feed(protocol.Shape(), protocol.MERGE, 2, *range(4))

        self.assertEqual(shape.produced, 2)


class PrintingTest(unittest.TestCase):
    def test_a_fresh_stream_prints_as_being_between_commands(self) -> None:
        self.assertIn("between commands", repr(protocol.Shape()))

    def test_and_one_mid_command_prints_which_command_it_is_in(self) -> None:
        self.assertIn("0x09", repr(feed(protocol.Shape(), protocol.MULTIPLY)))

    def test_and_what_the_part_still_owes(self) -> None:
        self.assertIn("4 owed", repr(feed(protocol.Shape(), protocol.MULTIPLY, 1, 0, 2, 0)))


if __name__ == "__main__":
    unittest.main()
