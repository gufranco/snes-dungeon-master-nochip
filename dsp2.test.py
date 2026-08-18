import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "dsp2.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dsp2", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dsp2 = load_module()


class TileTest(unittest.TestCase):
    def test_the_output_is_the_same_length_as_the_input(self):
        out = dsp2.tile(bytes(range(32)))

        self.assertEqual(len(out), 32)

    def test_an_all_zero_bitmap_converts_to_all_zero_planes(self):
        out = dsp2.tile(bytes(32))

        self.assertEqual(out, bytes(32))

    def test_a_solid_bitmap_lights_every_plane(self):
        out = dsp2.tile(bytes([0xFF] * 32))

        self.assertEqual(out, bytes([0xFF] * 32))

    def test_the_first_plane_pair_carries_bits_zero_and_four_of_each_input_byte(self):
        out = dsp2.tile(bytes([0x11] + [0x00] * 31))

        self.assertEqual(out[0], 0xC0)
        self.assertEqual(out[1], 0x00)

    def test_the_high_planes_land_in_the_second_half_of_the_output(self):
        out = dsp2.tile(bytes([0x88] + [0x00] * 31))

        self.assertEqual(out[:16], bytes(16))
        self.assertNotEqual(out[16:], bytes(16))

    def test_a_wrong_length_input_is_refused(self):
        with self.assertRaises(ValueError):
            dsp2.tile(bytes(31))

    def test_distinct_inputs_stay_distinct_across_a_byte_sweep(self):
        seen = {dsp2.tile(bytes([value] * 32)) for value in range(256)}

        self.assertEqual(len(seen), 256)


class TransparencyTest(unittest.TestCase):
    def test_the_colour_is_kept_as_a_nibble(self):
        state = dsp2.State()

        state.set_transparent(0xA7)

        self.assertEqual(state.transparent, 0x07)


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.state = dsp2.State()
        self.state.set_transparent(0x00)

    def test_an_opaque_overlay_replaces_the_background_entirely(self):
        under = bytes([0x11, 0x22])
        over = bytes([0x33, 0x44])

        out = dsp2.merge(self.state, under + over, 2)

        self.assertEqual(out, over)

    def test_a_fully_transparent_overlay_leaves_the_background(self):
        under = bytes([0x11, 0x22])
        over = bytes([0x00, 0x00])

        out = dsp2.merge(self.state, under + over, 2)

        self.assertEqual(out, under)

    def test_transparency_is_decided_per_nibble(self):
        under = bytes([0x12])
        over = bytes([0x30])

        out = dsp2.merge(self.state, under + over, 1)

        self.assertEqual(out, bytes([0x32]))

    def test_the_transparent_colour_is_whatever_was_last_set(self):
        self.state.set_transparent(0x0F)
        under = bytes([0x12])
        over = bytes([0xFF])

        out = dsp2.merge(self.state, under + over, 1)

        self.assertEqual(out, bytes([0x12]))

    def test_the_output_is_as_long_as_the_declared_length(self):
        out = dsp2.merge(self.state, bytes(20), 10)

        self.assertEqual(len(out), 10)

    def test_a_payload_that_is_not_twice_the_length_is_refused(self):
        with self.assertRaises(ValueError):
            dsp2.merge(self.state, bytes(19), 10)


class MirrorTest(unittest.TestCase):
    def test_the_bytes_are_reversed_and_the_nibbles_swapped(self):
        out = dsp2.mirror(bytes([0x12, 0x34, 0x56]), 3)

        self.assertEqual(out, bytes([0x65, 0x43, 0x21]))

    def test_mirroring_twice_returns_the_original(self):
        original = bytes([0x0A, 0xB1, 0x2C, 0xD3])

        out = dsp2.mirror(dsp2.mirror(original, 4), 4)

        self.assertEqual(out, original)

    def test_a_single_byte_only_swaps_its_nibbles(self):
        out = dsp2.mirror(bytes([0xAB]), 1)

        self.assertEqual(out, bytes([0xBA]))

    def test_a_payload_shorter_than_the_length_is_refused(self):
        with self.assertRaises(ValueError):
            dsp2.mirror(bytes(3), 4)


class MultiplyTest(unittest.TestCase):
    def test_a_product_is_returned_as_four_little_endian_bytes(self):
        out = dsp2.multiply(bytes([0x10, 0x00, 0x03, 0x00]))

        self.assertEqual(out, bytes([0x30, 0x00, 0x00, 0x00]))

    def test_the_full_width_product_does_not_overflow(self):
        out = dsp2.multiply(bytes([0xFF, 0xFF, 0xFF, 0xFF]))

        self.assertEqual(int.from_bytes(out, "little"), 0xFFFF * 0xFFFF)

    def test_multiplying_by_zero_gives_zero(self):
        out = dsp2.multiply(bytes([0x34, 0x12, 0x00, 0x00]))

        self.assertEqual(out, bytes(4))

    def test_the_operands_are_read_as_little_endian_words(self):
        out = dsp2.multiply(bytes([0x00, 0x01, 0x00, 0x01]))

        self.assertEqual(int.from_bytes(out, "little"), 0x100 * 0x100)


class ScaleTest(unittest.TestCase):
    def test_an_input_no_longer_than_the_output_copies_its_nibbles_in_order(self):
        payload = bytes([0x12, 0x34])

        out = dsp2.scale(payload, 4, 4)

        self.assertEqual(out[:2], payload)

    def test_nibbles_past_the_payload_are_padded_rather_than_raising(self):
        out = dsp2.scale(bytes([0x12, 0x34]), 4, 4)

        self.assertEqual(out[2:], bytes(2))

    def test_the_output_is_as_long_as_the_declared_output_length(self):
        out = dsp2.scale(bytes([0x12, 0x34, 0x56, 0x78]), 8, 3)

        self.assertEqual(len(out), 3)

    def test_shrinking_keeps_the_first_nibble(self):
        out = dsp2.scale(bytes([0xAB, 0xCD, 0xEF, 0x01]), 8, 2)

        self.assertEqual(out[0] >> 4, 0xA)

    def test_a_payload_shorter_than_half_the_input_length_is_refused(self):
        with self.assertRaises(ValueError):
            dsp2.scale(bytes(3), 8, 4)

    def test_every_observed_length_pair_produces_the_declared_size(self):
        for in_len, out_len in ((0x48, 0x26), (0x48, 0x32), (0x78, 0x3A), (0x78, 0x50)):
            payload = bytes(range(256))[: (in_len + 1) >> 1]

            out = dsp2.scale(payload, in_len, out_len)

            self.assertEqual(len(out), out_len)


class ChipTest(unittest.TestCase):
    def setUp(self):
        self.chip = dsp2.Chip()

    def drive(self, values):
        for value in values:
            self.chip.write(value)

    def read_all(self, count):
        return bytes(self.chip.read() for _ in range(count))

    def test_a_sync_produces_nothing_to_read(self):
        self.drive([0x0F])

        self.assertEqual(self.chip.pending_output, 0)

    def test_a_multiply_runs_when_its_fourth_parameter_arrives(self):
        self.drive([0x09, 0x10, 0x00, 0x03, 0x00])

        self.assertEqual(self.chip.pending_output, 4)
        self.assertEqual(self.read_all(4), bytes([0x30, 0x00, 0x00, 0x00]))

    def test_a_tile_conversion_runs_after_thirty_two_parameters(self):
        self.drive([0x01, *range(32)])

        self.assertEqual(self.chip.pending_output, 32)

    def test_the_transparent_colour_survives_into_the_next_merge(self):
        self.drive([0x03, 0x0F])
        self.drive([0x05, 1, 0x12, 0xFF])

        self.assertEqual(self.read_all(1), bytes([0x12]))

    def test_a_read_with_nothing_pending_returns_the_idle_byte(self):
        self.assertEqual(self.chip.read(), dsp2.IDLE_BYTE)

    def test_a_merge_takes_its_length_before_its_payload(self):
        self.drive([0x05, 2, 0x11, 0x22, 0x00, 0x00])

        self.assertEqual(self.chip.pending_output, 2)

    def test_a_scale_takes_two_lengths_before_its_payload(self):
        self.drive([0x0D, 4, 4, 0x12, 0x34])

        self.assertEqual(self.chip.pending_output, 4)

    def test_an_unknown_command_is_treated_as_a_sync(self):
        self.drive([0x02])

        self.assertEqual(self.chip.pending_output, 0)

    def test_two_transactions_in_a_row_both_produce_output(self):
        self.drive([0x09, 0x02, 0x00, 0x02, 0x00])
        first = self.read_all(4)
        self.drive([0x09, 0x03, 0x00, 0x03, 0x00])
        second = self.read_all(4)

        self.assertEqual(int.from_bytes(first, "little"), 4)
        self.assertEqual(int.from_bytes(second, "little"), 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
