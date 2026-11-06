import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import Any

import script

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
    image = bytearray(b"\x00" * size)
    image[0x7FC0:0x7FD5] = b"BLANK".ljust(21, b" ")
    image[0x7FD5] = 0x20
    image[0x7FD6] = 0x05
    image[0x7FD7] = 0x0A
    return bytes(image)


DECLARED = "blank-usa.sfc"

COPIER = bytes(0x200)


def declaring(dump: bytes) -> dict[str, Any]:
    return {
        "artifacts": [
            {
                "name": "Blank, USA",
                "filename": DECLARED,
                "accepted": [{"sha256": hashlib.sha256(dump).hexdigest()}],
            }
        ]
    }


def finished_run(
    source: Path, into: Path, target: Path, said: list[str], manifest: Any
) -> tuple[int, list[Any]]:
    ran: list[Any] = []

    def _assemble(argv: Any, **_kwargs: Any) -> int:
        ran.append(argv)
        target.write_bytes(blank())
        cartridge.symbols_beside(target).write_text(SYMBOLS)
        return 0

    code = cartridge.main(
        ["cartridge.py", str(source), str(into)],
        said.append,
        assemble=_assemble,
        staged=target,
        manifest=manifest,
    )
    return code, ran


class SymbolNameTest(unittest.TestCase):
    def test_it_sits_beside_the_image_it_describes(self) -> None:
        self.assertEqual(cartridge.symbols_beside("build/dm.sfc"), Path("build/dm.sym"))

    def test_a_name_with_no_suffix_still_gets_one(self) -> None:
        self.assertEqual(cartridge.symbols_beside("dm"), Path("dm.sym"))


class FinishTest(unittest.TestCase):
    def test_the_header_stops_declaring_a_coprocessor_and_keeps_the_battery(self) -> None:
        found = cartridge.finish(blank(), SYMBOLS)

        self.assertEqual(found[0x7FD6], cartridge.romimage.rewrite.CHIPSET_RAM_BATTERY)

    def test_the_image_keeps_its_size(self) -> None:
        found = cartridge.finish(blank(), SYMBOLS)

        self.assertEqual(len(found), 0x100000)

    def test_a_symbol_table_missing_a_name_is_refused(self) -> None:
        with self.assertRaises(cartridge.patch.MissingSymbol):
            cartridge.finish(blank(), "[labels]\n00:FBED b00_first\n")


class AssembleTest(unittest.TestCase):
    def test_it_hands_the_arguments_to_the_builder(self) -> None:
        said: list[str] = []

        code = cartridge.assemble(["build.py"], said.append)

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def test_a_missing_assembler_is_reported_rather_than_traced(self) -> None:
        # Arrange
        said: list[str] = []

        def absent(_argv: Any, **_kwargs: Any) -> int:
            raise cartridge.build.ToolchainMissing("asar is not in this environment")

        # Act
        code = cartridge.assemble(["build.py", "a.asm", "in.sfc", "out.sfc"], said.append, absent)

        # Assert
        self.assertEqual(code, 1)
        self.assertEqual(said, ["  asar is not in this environment"])


class ReportTest(unittest.TestCase):
    def test_a_finished_image_has_nothing_left(self) -> None:
        found = cartridge.unfinished(cartridge.finish(blank(), SYMBOLS))

        self.assertEqual(found, [])

    def test_an_image_that_still_declares_the_chip_says_so(self) -> None:
        found = cartridge.unfinished(blank())

        self.assertTrue(any("coprocessor" in line for line in found))


class CommandTest(unittest.TestCase):
    def test_it_asks_for_what_it_needs(self) -> None:
        said: list[str] = []

        code = cartridge.main(["cartridge.py"], said.append)

        self.assertEqual((code, "usage" in said[0]), (2, True))

    def test_a_missing_dump_is_reported_rather_than_opened(self) -> None:
        said: list[str] = []

        code = cartridge.main(["cartridge.py", "/nonexistent.sfc", "/out.sfc"], said.append)

        self.assertEqual((code, "no dump" in said[0]), (2, True))

    def test_a_build_that_fails_stops_there(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.sfc"
            source.write_bytes(blank())
            said: list[str] = []

            # Act
            code = cartridge.main(
                ["cartridge.py", str(source), str(Path(tmp) / "out.sfc")],
                said.append,
                assemble=lambda *_a, **_k: 1,
                manifest=declaring(blank()),
            )

        # Assert
        self.assertEqual(code, 1)

    def test_a_finished_build_reports_where_it_put_the_cartridge(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.sfc"
            source.write_bytes(blank())
            into = Path(tmp) / "dist"
            said: list[str] = []

            # Act
            code, _ = finished_run(source, into, Path(tmp) / "staged.sfc", said, declaring(blank()))

            # Assert
            name = cartridge.output_name(DECLARED)
            written = (into / cartridge.release_folder() / "emulator" / name).read_bytes()
            self.assertEqual((code, written[0x7FD6]), (0, 0x02))
            self.assertTrue(any(name in line for line in said))

    def test_a_dump_the_manifest_does_not_declare_is_refused_before_assembling(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.sfc"
            source.write_bytes(blank())
            said: list[str] = []

            # Act
            code, ran = finished_run(
                source, Path(tmp) / "dist", Path(tmp) / "staged.sfc", said, declaring(b"")
            )

            # Assert
            self.assertEqual((code, ran), (2, []))
            self.assertIn("tools/identify.py", "\n".join(said))

    def test_the_output_takes_the_manifest_name_whatever_the_dump_is_called(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "my copy (1).sfc"
            source.write_bytes(blank())

            # Act
            _, ran = finished_run(
                source, Path(tmp) / "dist", Path(tmp) / "staged.sfc", [], declaring(blank())
            )

            # Assert
            self.assertEqual(ran[0][-1], f"blank-usa-nochip-v{cartridge.version.VERSION}.sfc")

    def test_a_dump_behind_a_copier_header_is_identified_by_its_bare_bytes(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.smc"
            source.write_bytes(COPIER + blank())

            # Act
            code, _ = finished_run(
                source, Path(tmp) / "dist", Path(tmp) / "staged.sfc", [], declaring(blank())
            )

        # Assert
        self.assertEqual(code, 0)

    def test_the_release_lists_every_file_it_wrote_with_its_digest(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            into = Path(tmp) / "dist"
            source = Path(tmp) / "in.sfc"
            source.write_bytes(blank())

            # Act
            finished_run(source, into, Path(tmp) / "staged.sfc", [], declaring(blank()))

            # Assert
            release = into / cartridge.release_folder()
            rows = (release / cartridge.SUMS).read_text().splitlines()
            listed = {name: digest for digest, name in (row.split("  ") for row in rows)}
            self.assertEqual(
                sorted(name.split("/")[0] for name in listed), sorted(cartridge.DEVICES)
            )
            self.assertEqual(
                listed,
                {
                    name: hashlib.sha256((release / name).read_bytes()).hexdigest()
                    for name in listed
                },
            )

    def test_an_image_the_patch_did_not_finish_fails_the_build(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.sfc"
            source.write_bytes(blank())
            target = Path(tmp) / "out.sfc"

            def _assemble(_argv: Any, **_kwargs: Any) -> int:
                target.write_bytes(blank())
                cartridge.symbols_beside(target).write_text(SYMBOLS)
                return 0

            said: list[str] = []

            # Act
            code = cartridge.main(
                ["cartridge.py", str(source), str(target)],
                said.append,
                assemble=_assemble,
                left=lambda _image: ["something still reaches the chip"],
                staged=target,
                manifest=declaring(blank()),
            )

        # Assert
        self.assertEqual((code, "still reaches" in "\n".join(said)), (1, True))


class DeviceTest(unittest.TestCase):
    def finished(self) -> bytes:
        image = bytearray(cartridge.finish(blank(), SYMBOLS))
        image[0x7FD8] = 0x05
        declared: bytes = cartridge.romimage.rewrite.declare_rom_only(image)
        return declared

    def test_every_device_gets_its_own_folder(self) -> None:
        # Arrange
        final = self.finished()

        # Act
        forms = cartridge.forms_of("dm-nochip-v1.0.0.sfc", final)

        # Assert
        self.assertEqual([name.split("/")[0] for name, _ in forms], list(cartridge.DEVICES))

    def test_every_cartridge_but_the_game_doctor_takes_the_image_as_built(self) -> None:
        # Arrange
        final = self.finished()

        # Act
        forms = dict(cartridge.forms_of("dm-nochip-v1.0.0.sfc", final))

        # Assert
        self.assertEqual(
            [forms[f"{device}/dm-nochip-v1.0.0.sfc"] for device in cartridge.DEVICES[:4]],
            [final] * 4,
        )

    def test_the_game_doctor_gets_its_header_then_the_image(self) -> None:
        # Arrange
        final = self.finished()

        # Act
        written = dict(cartridge.forms_of("dm-nochip-v1.0.0.sfc", final))[
            "gamedoctor/dm-nochip-v1.0.0.smc"
        ]

        # Assert
        self.assertEqual((written[:16], written[0x200:]), (b"GAME DOCTOR SF 3", final))

    def test_its_map_is_ucon64s_eight_megabit_table_with_save_ram(self) -> None:
        # Arrange
        final = self.finished()

        # Act
        written = dict(cartridge.forms_of("dm-nochip-v1.0.0.sfc", final))[
            "gamedoctor/dm-nochip-v1.0.0.smc"
        ]

        # Assert
        self.assertEqual(
            (written[0x10], written[0x11:0x29]),
            (0x80, bytes([0x20, 0x21] * 9 + [0x20, 0x40, 0x20, 0x21, 0x20, 0x40])),
        )

    def test_the_release_folder_is_the_version(self) -> None:
        # Arrange
        release = "1.2.3"

        # Act
        folder = cartridge.release_folder(release)

        # Assert
        self.assertEqual(folder, "v1.2.3")

    def test_the_output_is_named_after_the_dump_and_the_version(self) -> None:
        # Arrange
        source = "external/roms/dungeon-master-usa.sfc"

        # Act
        name = cartridge.output_name(source, "1.2.3")

        # Assert
        self.assertEqual(name, "dungeon-master-usa-nochip-v1.2.3.sfc")


script.entry(__name__, unittest.main)
