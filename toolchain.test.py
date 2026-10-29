import importlib.util
import unittest
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).resolve().parent / "toolchain.py"


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("toolchain", MODULE_PATH)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


toolchain = load_module()


class CommandTest(unittest.TestCase):
    def test_a_program_runs_from_the_repository_root(self) -> None:
        # Arrange
        program = "dmemu"

        # Act
        found = toolchain.command(program)

        # Assert
        self.assertEqual(found, ["env", f"--chdir={MODULE_PATH.parent}", "dmemu"])

    def test_settings_come_before_the_program_and_arguments_after(self) -> None:
        # Arrange
        settings = ["SFSCAN=1", "SFGRID=1"]
        args = ["build/a.sfc", "600"]

        # Act
        found = toolchain.command("dmemu", settings, args)

        # Assert
        self.assertEqual(found[2:], ["SFSCAN=1", "SFGRID=1", "dmemu", "build/a.sfc", "600"])

    def test_a_program_can_run_from_another_folder(self) -> None:
        # Arrange
        where = Path("/work/build")

        # Act
        found = toolchain.command("asar", (), ["p.asm"], where)

        # Assert
        self.assertEqual(found[:2], ["env", "--chdir=/work/build"])

    def test_no_container_is_started_from_inside_one(self) -> None:
        # Arrange
        args = ["p.asm", "rom.sfc"]

        # Act
        found = toolchain.command("asar", (), args)

        # Assert
        self.assertNotIn("docker", found)


class ProgramsTest(unittest.TestCase):
    def test_the_image_carries_the_assembler_and_the_emulator(self) -> None:
        # Arrange
        expected = ("asar", "dmemu")

        # Act
        found = toolchain.PROGRAMS

        # Assert
        self.assertEqual(found, expected)

    def test_every_program_is_copied_into_the_runtime_image(self) -> None:
        # Arrange
        dockerfile = (MODULE_PATH.parent / "Dockerfile").read_text()
        runtime = dockerfile.split(" AS runtime\n", 1)[1].split(" AS gates\n", 1)[0]

        # Act
        found = [name for name in toolchain.PROGRAMS if f"/usr/local/bin/{name}\n" in runtime]

        # Assert
        self.assertEqual(found, list(toolchain.PROGRAMS))


class LauncherTest(unittest.TestCase):
    def test_a_command_names_both_launchers(self) -> None:
        # Arrange
        script = "pack.py"

        # Act
        found = toolchain.launched(script)

        # Assert
        self.assertEqual(found, "./run.sh pack.py, or on Windows .\\run.cmd pack.py")

    def test_both_launchers_sit_at_the_repository_root(self) -> None:
        # Arrange
        names = ("run.sh", "run.ps1", "run.cmd")

        # Act
        found = [(MODULE_PATH.parent / name).is_file() for name in names]

        # Assert
        self.assertEqual(found, [True, True, True])

    def test_a_missing_program_is_named_with_the_way_to_reach_it(self) -> None:
        # Arrange
        program = "asar"

        # Act
        found = toolchain.missing_message(program)

        # Assert
        self.assertTrue(found.startswith("asar is not in this environment."))
        self.assertIn("./run.sh <script>", found)


if __name__ == "__main__":
    unittest.main()
