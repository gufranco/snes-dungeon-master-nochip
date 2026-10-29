import contextlib
import importlib.util
import io
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).resolve().parent / "build.py"


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("build", MODULE_PATH)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bd = load_module()


def _recording(seen: list[Any]) -> Callable[[list[str]], int]:

    def _run(args: list[str]) -> int:
        seen.append(args)
        return 0

    return _run


def _present(_program: str) -> str:
    return "/usr/local/bin/asar"


def _absent(_program: str) -> None:
    return None


class StagedPathTest(unittest.TestCase):
    def test_it_lands_beside_the_source_being_assembled(self) -> None:
        found = bd.staged_path("/somewhere/asm/nochip.asm", "out.sfc")

        self.assertEqual(found, Path("/somewhere/asm/out.sfc"))


class ImageTest(unittest.TestCase):
    def test_the_assembler_is_the_one_the_image_carries(self) -> None:
        # Arrange
        work = Path("/w")

        # Act
        args = bd.patch_command(work, "p.asm", "rom.sfc")

        # Assert
        self.assertIn("asar", args)
        self.assertNotIn("docker", args)

    def test_the_assembly_sources_sit_where_the_cartridge_looks(self) -> None:
        # Arrange
        expected = MODULE_PATH.parent / "asm"

        # Act
        found = bd.ASM_DIR

        # Assert
        self.assertEqual(found, expected)
        self.assertTrue((found / "nochip.asm").exists())


class CommandTest(unittest.TestCase):
    def test_the_assembler_runs_in_the_folder_of_the_patch(self) -> None:
        # Arrange
        work = Path("/w")

        # Act
        args = bd.patch_command(work, "p.asm", "rom.sfc")

        # Assert
        self.assertEqual(args[:2], ["env", "--chdir=/w"])

    def test_the_patch_and_the_image_are_named_last(self) -> None:
        # Arrange
        work = Path("/w")

        # Act
        args = bd.patch_command(work, "p.asm", "rom.sfc")

        # Assert
        self.assertEqual(args[-2:], ["p.asm", "rom.sfc"])

    def test_no_container_is_started_from_inside_one(self) -> None:
        # Arrange
        work = Path("/w")

        # Act
        args = bd.patch_command(work, "p.asm", "rom.sfc")

        # Assert
        self.assertNotIn("--network=none", args)

    def test_the_label_table_is_asked_for_beside_the_image(self) -> None:
        args = bd.patch_command(Path("/w"), "p.asm", "rom.sfc")

        self.assertIn("--symbols=wla", args)
        self.assertIn("--symbols-path=rom.sym", args)

    def test_paths_are_passed_as_names_not_host_paths(self) -> None:
        args = bd.patch_command(Path("/some/host/dir"), "patch.asm", "rom.sfc")

        self.assertNotIn("/some/host/dir/patch.asm", args)


class ToolchainTest(unittest.TestCase):
    def test_an_absent_assembler_says_to_start_through_the_launcher(self) -> None:
        # Arrange
        look = _absent

        # Act
        with self.assertRaises(bd.ToolchainMissing) as raised:
            bd.require("asar", look)

        # Assert
        self.assertIn("./run.sh <script>", str(raised.exception))

    def test_a_present_assembler_is_let_through(self) -> None:
        # Arrange
        look = _present

        # Act
        found = bd.require("asar", look)

        # Assert
        self.assertIsNone(found)

    def test_an_absent_program_is_named_rather_than_traced(self) -> None:
        # Arrange
        program = "definitely-not-a-real-program-9f3a"

        # Act
        with self.assertRaises(bd.ToolchainMissing) as raised:
            bd.run([program, "--version"], say=lambda _line: None)

        # Assert
        self.assertIn(program, str(raised.exception))

    def test_an_absent_toolchain_exits_one_and_says_so_on_stderr(self) -> None:
        # Arrange
        def absent() -> Any:
            raise bd.ToolchainMissing("asar is not in this environment")

        original, bd.main = bd.main, absent
        stderr = io.StringIO()

        # Act
        try:
            with contextlib.redirect_stderr(stderr):
                code = bd.cli()
        finally:
            bd.main = original

        # Assert
        self.assertEqual(code, 1)
        self.assertIn("asar is not in this environment", stderr.getvalue())

    def test_a_reachable_program_returns_its_own_exit_code(self) -> None:
        # Arrange
        quiet = lambda _line: None  # noqa: E731

        # Act
        found = (bd.run(["true"], say=quiet), bd.run(["false"], say=quiet))

        # Assert
        self.assertEqual(found, (0, 1))


class SafetyTest(unittest.TestCase):
    def test_a_rom_is_copied_before_patching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            rom = work / "orig.sfc"
            rom.write_bytes(b"x" * 1024)

            out = bd.stage_rom(rom, work, "out.sfc")

            self.assertTrue(out.exists())
            self.assertEqual(out.read_bytes(), rom.read_bytes())
            self.assertNotEqual(out, rom)

    def test_staging_never_overwrites_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            rom = work / "orig.sfc"
            rom.write_bytes(b"A" * 512)

            out = bd.stage_rom(rom, work, "out.sfc")
            out.write_bytes(b"B" * 512)

            self.assertEqual(rom.read_bytes(), b"A" * 512)


class RunTest(unittest.TestCase):
    def test_a_command_is_printed_before_it_runs(self) -> None:
        # Arrange
        said: list[Any] = []

        # Act
        bd.run(["asar", "p.asm"], execute=lambda _args: 0, say=said.append)

        # Assert
        self.assertIn("asar p.asm", said[0])

    def test_and_what_it_returned_comes_back(self) -> None:
        self.assertEqual(bd.run(["x"], execute=lambda _args: 3, say=lambda _line: None), 3)


class StagingTest(unittest.TestCase):
    def test_patching_the_source_in_place_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            (where / "in.sfc").write_bytes(b"\x00" * 16)

            with self.assertRaises(ValueError):
                bd.stage_rom(where / "in.sfc", where, "in.sfc")


class ShellingOutTest(unittest.TestCase):
    def test_with_nothing_passed_in_it_runs_the_command_itself(self) -> None:
        code = bd.run(["true"], say=lambda _line: None)

        self.assertEqual(code, 0)


class EntryTest(unittest.TestCase):
    def test_the_old_image_flag_is_now_a_usage_error(self) -> None:
        # Arrange
        said: list[Any] = []

        # Act
        code = bd.main(["bd.py", "--image"], say=lambda _l: None, complain=said.append)

        # Assert
        self.assertEqual(code, 2)
        self.assertEqual(said, ["usage: build.py <patch.asm> <source-rom> <output-rom>"])

    def test_too_few_arguments_are_refused_with_the_usage(self) -> None:
        said: list[Any] = []

        code = bd.main(["bd.py", "patch.asm"], say=lambda _l: None, complain=said.append)

        self.assertEqual(code, 2)
        self.assertIn("usage", said[0])

    def test_an_absent_assembler_stops_before_anything_is_staged(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            (where / "in.sfc").write_bytes(b"\x00" * 32)
            argv = ["bd.py", str(where / "patch.asm"), str(where / "in.sfc"), "out.sfc"]

            # Act
            with self.assertRaises(bd.ToolchainMissing) as raised:
                bd.main(argv, execute=lambda _args: 0, say=lambda _l: None, look=_absent)

            # Assert
            self.assertIn("asar", str(raised.exception))
            self.assertFalse((where / "out.sfc").exists())

    def test_a_whole_run_stages_the_rom_and_patches_it(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            (where / "patch.asm").write_text("; nothing")
            (where / "in.sfc").write_bytes(b"\x00" * 32)
            ran: list[Any] = []

            # Act
            code = bd.main(
                ["bd.py", str(where / "patch.asm"), str(where / "in.sfc"), "out.sfc"],
                execute=_recording(ran),
                say=lambda _l: None,
                look=_present,
            )

            # Assert
            self.assertEqual(code, 0)
            self.assertEqual(len(ran), 1)
            self.assertTrue((where / "out.sfc").exists())

    def test_a_patch_that_fails_is_reported_as_what_it_returned(self) -> None:
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            (where / "patch.asm").write_text("; nothing")
            (where / "in.sfc").write_bytes(b"\x00" * 32)
            answers = iter([4])

            # Act
            code = bd.main(
                ["bd.py", str(where / "patch.asm"), str(where / "in.sfc"), "out.sfc"],
                execute=lambda _args: next(answers),
                say=lambda _l: None,
                look=_present,
            )

            # Assert
            self.assertEqual(code, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
