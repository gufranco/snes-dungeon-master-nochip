import importlib.util
import tempfile
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


cartridge = load_module("cartridge", ROOT / "cartridge.py")

SYMBOLS = """; wla symbolic information file

[labels]
00:FBED b00_first
00:FBF5 b00_feed
00:FBFA b00_drain
04:AA1B b04_0080
04:AA20 b04_0084
04:AA25 b04_0088
04:AA2A b04_008C
9C:E203 dsp_write
9C:E21E dsp_read
"""


def blank(size: int = 0x100000) -> bytes:
    """An image with a LoROM header and nothing in it that reaches the chip."""
    image = bytearray(b"\x00" * size)
    image[0x7FC0:0x7FD5] = b"BLANK".ljust(21, b" ")
    image[0x7FD5] = 0x20
    image[0x7FD6] = 0x05
    image[0x7FD7] = 0x0A
    return bytes(image)


class SymbolNameTest(unittest.TestCase):
    """Where the label table for an image is written."""

    def test_it_sits_beside_the_image_it_describes(self) -> None:
        self.assertEqual(cartridge.symbols_beside("build/dm.sfc"), Path("build/dm.sym"))

    def test_a_name_with_no_suffix_still_gets_one(self) -> None:
        self.assertEqual(cartridge.symbols_beside("dm"), Path("dm.sym"))


class FinishTest(unittest.TestCase):
    """Turning an assembled image into one that needs no coprocessor."""

    def test_the_header_stops_declaring_a_coprocessor(self) -> None:
        found = cartridge.finish(blank(), SYMBOLS)

        self.assertEqual(found[0x7FD6], cartridge.romimage.CHIPSET_ROM_ONLY)

    def test_the_image_keeps_its_size(self) -> None:
        found = cartridge.finish(blank(), SYMBOLS)

        self.assertEqual(len(found), 0x100000)

    def test_a_symbol_table_missing_a_name_is_refused(self) -> None:
        with self.assertRaises(cartridge.patch.MissingSymbol):
            cartridge.finish(blank(), "[labels]\n00:FBED b00_first\n")


class AssembleTest(unittest.TestCase):
    """The step that shells out, asked to do nothing."""

    def test_it_hands_the_arguments_to_the_builder(self) -> None:
        said: list[str] = []

        code = cartridge.assemble(["build.py"], said.append)

        self.assertEqual((code, "usage" in said[0]), (2, True))


class ReportTest(unittest.TestCase):
    """What is still pointing at the chip, said out loud."""

    def test_a_finished_image_has_nothing_left(self) -> None:
        found = cartridge.unfinished(cartridge.finish(blank(), SYMBOLS))

        self.assertEqual(found, [])

    def test_an_image_that_still_declares_the_chip_says_so(self) -> None:
        found = cartridge.unfinished(blank())

        self.assertTrue(any("coprocessor" in line for line in found))


class CommandTest(unittest.TestCase):
    """The command line."""

    def test_it_asks_for_what_it_needs(self) -> None:
        said: list[str] = []

        code = cartridge.main(["cartridge.py"], said.append)

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def test_a_missing_dump_is_reported_rather_than_opened(self) -> None:
        said: list[str] = []

        code = cartridge.main(["cartridge.py", "/nonexistent.sfc", "/out.sfc"], said.append)

        self.assertEqual((code, "no dump" in said[0]), (2, True))

    def test_a_build_that_fails_stops_there(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.sfc"
            source.write_bytes(blank())
            said: list[str] = []

            code = cartridge.main(
                ["cartridge.py", str(source), str(Path(tmp) / "out.sfc")],
                said.append,
                assemble=lambda *_a, **_k: 1,
            )

        self.assertEqual(code, 1)

    def test_a_finished_build_reports_where_it_put_the_cartridge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.sfc"
            source.write_bytes(blank())
            target = Path(tmp) / "out.sfc"

            def _assemble(_argv: Any, **_kwargs: Any) -> int:
                target.write_bytes(blank())
                cartridge.symbols_beside(target).write_text(SYMBOLS)
                return 0

            said: list[str] = []

            code = cartridge.main(
                ["cartridge.py", str(source), str(target)],
                said.append,
                assemble=_assemble,
                staged=target,
            )

            self.assertEqual((code, target.read_bytes()[0x7FD6]), (0, 0x00))

        self.assertTrue(any("out.sfc" in line for line in said))

    def test_an_image_the_patch_did_not_finish_fails_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.sfc"
            source.write_bytes(blank())
            target = Path(tmp) / "out.sfc"

            def _assemble(_argv: Any, **_kwargs: Any) -> int:
                target.write_bytes(blank())
                cartridge.symbols_beside(target).write_text(SYMBOLS)
                return 0

            said: list[str] = []

            code = cartridge.main(
                ["cartridge.py", str(source), str(target)],
                said.append,
                assemble=_assemble,
                left=lambda _image: ["something still reaches the chip"],
                staged=target,
            )

        self.assertEqual((code, "still reaches" in "\n".join(said)), (1, True))


if __name__ == "__main__":
    unittest.main()
