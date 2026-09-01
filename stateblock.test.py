import importlib.util
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stateblock = load_module("stateblock", ROOT / "stateblock.py")


class ReadingTest(unittest.TestCase):
    """The fields the assembly declares, as offsets and widths."""

    def test_it_reads_a_field_and_its_offset(self) -> None:
        found = stateblock.fields("!S_STAGE        = $00           ; 0 idle\n")

        self.assertEqual(found, {"!S_STAGE": (0x00, 1)})

    def test_a_width_stated_in_the_comment_is_taken(self) -> None:
        found = stateblock.fields(
            "!S_WANT_PARAM   = $05           ; bytes still to arrive, 16 bit\n"
        )

        self.assertEqual(found["!S_WANT_PARAM"], (0x05, 2))

    def test_a_field_with_no_width_stated_is_one_byte(self) -> None:
        found = stateblock.fields("!S_COMMAND      = $01           ; the command byte in flight\n")

        self.assertEqual(found["!S_COMMAND"], (0x01, 1))

    def test_a_width_stated_on_a_later_line_is_taken(self) -> None:
        text = "!S_XFER_PTR     = $10           ; 24 bit pointer the transfer indexes\n"

        self.assertEqual(stateblock.fields(text)["!S_XFER_PTR"], (0x10, 3))

    def test_a_line_that_declares_no_field_is_left_out(self) -> None:
        self.assertEqual(stateblock.fields("; just a comment\n\n"), {})

    def test_a_name_that_is_not_a_field_of_the_block_is_left_out(self) -> None:
        found = stateblock.fields("!P_BUFFER       = $000A00       ; parameters\n")

        self.assertEqual(found, {})

    def test_a_field_addressed_outside_the_page_is_left_out(self) -> None:
        found = stateblock.fields("!S_ELSEWHERE    = $000A00       ; not on the page\n")

        self.assertEqual(found, {})

    def test_the_scratch_region_reaches_the_end_of_the_page_by_default(self) -> None:
        found = stateblock.fields("!S_SCRATCH      = $28           ; working room\n")

        self.assertEqual(found["!S_SCRATCH"], (0x28, stateblock.PAGE - 0x28))

    def test_the_scratch_region_stops_where_the_assembly_says_it_stops(self) -> None:
        text = "!S_SCRATCH      = $28           ; working room\n!S_SCRATCH_END  = $F0\n"

        self.assertEqual(stateblock.fields(text)["!S_SCRATCH"], (0x28, 0xF0 - 0x28))

    def test_the_end_marker_is_not_itself_a_field(self) -> None:
        text = "!S_SCRATCH      = $28           ; working room\n!S_SCRATCH_END  = $F0\n"

        self.assertNotIn("!S_SCRATCH_END", stateblock.fields(text))

    def test_the_block_move_stub_is_an_instruction_rather_than_a_value(self) -> None:
        found = stateblock.fields("!S_MVN          = $20           ; a four byte MVN stub\n")

        self.assertEqual(found["!S_MVN"], (0x20, stateblock.STUB_BYTES))


class OverlapTest(unittest.TestCase):
    """Two fields that share a byte, which is the failure this exists to catch."""

    def test_fields_that_do_not_touch_are_clear(self) -> None:
        self.assertEqual(stateblock.overlaps({"a": (0, 1), "b": (1, 1)}), [])

    def test_a_field_landing_on_another_is_reported_both_ways(self) -> None:
        found = stateblock.overlaps({"a": (0x0E, 1), "b": (0x0E, 2)})

        self.assertEqual(found, [("a", "b", 0x0E)])

    def test_a_wide_field_reaching_into_the_next_is_reported(self) -> None:
        found = stateblock.overlaps({"a": (0x10, 3), "b": (0x12, 1)})

        self.assertEqual(found, [("a", "b", 0x12)])

    def test_the_report_names_the_first_byte_they_share(self) -> None:
        found = stateblock.overlaps({"a": (0x20, 4), "b": (0x22, 2)})

        self.assertEqual(found[0][2], 0x22)


class BlockTest(unittest.TestCase):
    """The block as the assembly actually declares it."""

    def test_no_two_fields_share_a_byte(self) -> None:
        found = stateblock.overlaps(stateblock.fields(stateblock.SOURCE.read_text()))

        self.assertEqual(
            found,
            [],
            "\n".join(f"{one} and {two} share ${at:02X}" for one, two, at in found),
        )

    def test_every_field_fits_the_direct_page_the_block_owns(self) -> None:
        declared = stateblock.fields(stateblock.SOURCE.read_text())

        past = [name for name, (at, width) in declared.items() if at + width > stateblock.PAGE]

        self.assertEqual(past, [])

    def test_the_block_declares_the_fields_the_routines_use(self) -> None:
        declared = stateblock.fields(stateblock.SOURCE.read_text())

        self.assertIn("!S_INBYTE", declared)
        self.assertIn("!S_OVERLAY", declared)


if __name__ == "__main__":
    unittest.main()
