import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


similarity = load_module("similarity", ROOT / "similarity.py")

ASSEMBLY = "\n".join(
    (
        "; a comment",
        "!ROUTINES = $9CE1BF",
        "!BANK00   = $00FBED",
        "!BANK04   = $04AA1B",
        "org !ROUTINES",
    )
)

SYMBOLS = {
    "routines_end": (0x9C, 0xE200),
    "bank00_end": (0x00, 0xFC00),
    "bank04_end": (0x04, 0xAB00),
}

HEADER_AT = 0x7FC0


def a_cartridge(size: int = 0x10000) -> bytes:
    """An image carrying a header the library will recognise and rewrite."""
    from romimage import rewrite

    image = bytearray(size)
    image[HEADER_AT : HEADER_AT + 21] = b"TEST CARTRIDGE       "
    image[HEADER_AT + 0x15] = 0x20
    image[HEADER_AT + 0x16] = 0x02
    image[HEADER_AT + 0x17] = 0x0B
    image[HEADER_AT + 0x19] = 0x01
    image[HEADER_AT + 0x1A] = 0x33
    value = rewrite.checksum(image, [HEADER_AT])
    image[HEADER_AT + 0x1C] = (value ^ 0xFFFF) & 0xFF
    image[HEADER_AT + 0x1D] = (value ^ 0xFFFF) >> 8
    image[HEADER_AT + 0x1E] = value & 0xFF
    image[HEADER_AT + 0x1F] = value >> 8
    return bytes(image)


class DefineTest(unittest.TestCase):
    """The bare addresses the assembly declares."""

    def test_every_declared_address_is_read(self) -> None:
        found = similarity.defines(ASSEMBLY)

        self.assertEqual(found["ROUTINES"], 0x9CE1BF)

    def test_a_comment_declares_nothing(self) -> None:
        found = similarity.defines("; !NOTHING = $010000")

        self.assertEqual(found, {})

    def test_a_long_address_splits_into_bank_and_address(self) -> None:
        found = similarity.bank_and_address(0x9CE1BF)

        self.assertEqual(found, (0x9C, 0xE1BF))


class FillerTest(unittest.TestCase):
    """The runs of unused space the assembler wrote into."""

    def test_each_declared_run_covers_the_code_written_into_it(self) -> None:
        found = similarity.filler(ASSEMBLY, SYMBOLS)

        self.assertEqual(len(found["routines"]), 0xE200 - 0xE1BF)

    def test_a_run_starts_where_the_assembly_says_it_does(self) -> None:
        found = similarity.filler(ASSEMBLY, SYMBOLS)

        self.assertEqual(min(found["routines"]), 0x0E61BF)

    def test_every_declared_run_is_accounted_for(self) -> None:
        found = similarity.filler(ASSEMBLY, SYMBOLS)

        self.assertEqual(len(found), len(similarity.FILLER))

    def test_a_missing_declaration_is_refused(self) -> None:
        with self.assertRaises(similarity.NoRegion) as caught:
            similarity.filler("!BANK00 = $00FBED\n!BANK04 = $04AA1B", SYMBOLS)

        self.assertIn("ROUTINES", str(caught.exception))

    def test_a_missing_label_is_refused(self) -> None:
        without = {name: where for name, where in SYMBOLS.items() if name != "routines_end"}

        with self.assertRaises(similarity.NoRegion) as caught:
            similarity.filler(ASSEMBLY, without)

        self.assertIn("routines_end", str(caught.exception))

    def test_a_label_before_its_base_is_refused(self) -> None:
        backwards = dict(SYMBOLS, routines_end=(0x9C, 0xE100))

        with self.assertRaises(similarity.NoRegion) as caught:
            similarity.filler(ASSEMBLY, backwards)

        self.assertIn("before", str(caught.exception))


class HeaderTest(unittest.TestCase):
    """The fields that declare a plain cartridge."""

    def test_every_field_of_every_mirror_is_claimed(self) -> None:
        found = similarity.header(a_cartridge())

        self.assertEqual(found, {HEADER_AT + one for one in similarity.HEADER_FIELDS})

    def test_an_image_with_no_header_claims_nothing(self) -> None:
        found = similarity.header(bytes(0x10000))

        self.assertEqual(found, set())

    def test_it_claims_every_byte_a_declaration_would_write(self) -> None:
        from romimage import rewrite

        image = a_cartridge()
        declared = rewrite.declare_rom_only(image)

        moved = {at for at in range(len(image)) if image[at] != declared[at]}
        self.assertTrue(moved <= similarity.header(image))


class DifferenceTest(unittest.TestCase):
    """Where two images disagree."""

    def test_it_names_every_byte_that_moved(self) -> None:
        retail = bytes(16)
        final = bytes([0, 1]) + bytes(13) + bytes([9])

        self.assertEqual(similarity.differences(retail, final), [1, 15])

    def test_identical_images_disagree_nowhere(self) -> None:
        found = similarity.differences(bytes(16), bytes(16))

        self.assertEqual(found, [])

    def test_images_of_different_sizes_are_refused(self) -> None:
        with self.assertRaises(similarity.NoRegion) as caught:
            similarity.differences(bytes(16), bytes(17))

        self.assertIn("16", str(caught.exception))


class ClaimTest(unittest.TestCase):
    """Everything entitled to differ, gathered."""

    def test_the_redirected_instructions_are_claimed(self) -> None:
        found = similarity.claims(a_cartridge(), ASSEMBLY, SYMBOLS)

        self.assertIn("redirected sites", found)

    def test_the_header_is_claimed(self) -> None:
        found = similarity.claims(a_cartridge(), ASSEMBLY, SYMBOLS)

        self.assertEqual(found["header"], similarity.header(a_cartridge()))


class AccountTest(unittest.TestCase):
    """Which region each differing byte belongs to."""

    def test_a_byte_inside_a_declared_run_is_counted_to_it(self) -> None:
        retail = bytearray(a_cartridge(0x100000))
        final = bytearray(retail)
        final[0x0E61BF] = 0xAB

        found = similarity.account(retail, final, ASSEMBLY, SYMBOLS)

        self.assertEqual(found.counted["routines"], 1)

    def test_a_byte_outside_every_region_is_loose(self) -> None:
        retail = bytearray(a_cartridge(0x100000))
        final = bytearray(retail)
        final[0x001234] = 0xAB

        found = similarity.account(retail, final, ASSEMBLY, SYMBOLS)

        self.assertEqual(found.loose, [0x001234])

    def test_an_image_with_nothing_loose_is_settled(self) -> None:
        retail = bytearray(a_cartridge(0x100000))
        final = bytearray(retail)
        final[0x0E61BF] = 0xAB

        found = similarity.account(retail, final, ASSEMBLY, SYMBOLS)

        self.assertTrue(found.ok)

    def test_an_image_with_a_loose_byte_is_not_settled(self) -> None:
        retail = bytearray(a_cartridge(0x100000))
        final = bytearray(retail)
        final[0x001234] = 0xAB

        found = similarity.account(retail, final, ASSEMBLY, SYMBOLS)

        self.assertFalse(found.ok)

    def test_every_differing_byte_is_either_counted_or_loose(self) -> None:
        retail = bytearray(a_cartridge(0x100000))
        final = bytearray(retail)
        final[0x0E61BF] = 0xAB
        final[0x001234] = 0xCD

        found = similarity.account(retail, final, ASSEMBLY, SYMBOLS)

        self.assertEqual(found.differ, 2)


class ExplainTest(unittest.TestCase):
    """How a result reads."""

    def test_a_settled_result_says_every_byte_was_declared(self) -> None:
        report = similarity.Report(differ=3, counted={"routines": 3}, loose=[])

        found = similarity.explain(report, bytes(16), bytes(16))

        self.assertIn("every one of them", found)

    def test_a_settled_result_names_each_region_and_its_count(self) -> None:
        report = similarity.Report(differ=3, counted={"routines": 3}, loose=[])

        found = similarity.explain(report, bytes(16), bytes(16))

        self.assertIn("routines", found)

    def test_a_loose_byte_is_shown_with_both_values(self) -> None:
        report = similarity.Report(differ=1, counted={}, loose=[2])

        found = similarity.explain(report, bytes([0, 0, 0x11]), bytes([0, 0, 0x22]))

        self.assertIn("0x11 -> 0x22", found)

    def test_more_loose_bytes_than_it_shows_are_counted(self) -> None:
        many = list(range(similarity.EXAMPLE_LIMIT + 3))
        report = similarity.Report(differ=len(many), counted={}, loose=many)

        found = similarity.explain(report, bytes(32), bytes(32))

        self.assertIn("and 3 more", found)


class MainTest(unittest.TestCase):
    """The one command."""

    @override
    def setUp(self) -> None:
        self.kept = (
            similarity.assembled.ASSEMBLY,
            similarity.assembled.SYMBOLS,
            similarity.assembled.stale,
        )

    @override
    def tearDown(self) -> None:
        (
            similarity.assembled.ASSEMBLY,
            similarity.assembled.SYMBOLS,
            similarity.assembled.stale,
        ) = self.kept

    def staged(self, tmp: str, final: bytes) -> list[str]:
        where = Path(tmp)
        (where / "dump.sfc").write_bytes(a_cartridge(0x100000))
        (where / "final.sfc").write_bytes(final)
        (where / "nochip.asm").write_text(ASSEMBLY)
        (where / "dm-sym.sym").write_text(
            "\n".join(f"{bank:02X}:{addr:04X} {name}" for name, (bank, addr) in SYMBOLS.items())
        )
        similarity.assembled.ASSEMBLY = where / "nochip.asm"
        similarity.assembled.SYMBOLS = where / "dm-sym.sym"
        similarity.assembled.stale = lambda: None
        return ["similarity.py", str(where / "dump.sfc"), str(where / "final.sfc")]

    def test_the_wrong_number_of_arguments_is_refused(self) -> None:
        said: list[str] = []

        code = similarity.main(["similarity.py"], said.append)

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def test_a_stale_image_is_reported_rather_than_compared(self) -> None:
        said: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            argv = self.staged(tmp, a_cartridge(0x100000))
            similarity.assembled.stale = lambda: "the table predates the image"
            code = similarity.main(argv, said.append)

        self.assertEqual((code, "predates" in said[0]), (2, True))

    def test_a_cartridge_that_stays_inside_its_regions_passes(self) -> None:
        final = bytearray(a_cartridge(0x100000))
        final[0x0E61BF] = 0xAB

        with tempfile.TemporaryDirectory() as tmp:
            code = similarity.main(self.staged(tmp, bytes(final)), lambda _line: None)

        self.assertEqual(code, 0)

    def test_a_cartridge_with_a_byte_outside_them_fails(self) -> None:
        final = bytearray(a_cartridge(0x100000))
        final[0x001234] = 0xAB

        with tempfile.TemporaryDirectory() as tmp:
            code = similarity.main(self.staged(tmp, bytes(final)), lambda _line: None)

        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
