import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / "run.sh"
SYSTEM_PATH = "/usr/bin:/bin"
FAKE_DOCKER = """#!/bin/sh
printf '%s\\n' "$*" >> "$DOCKER_LOG"
if [ "$1" = "info" ]; then
  exit "${DOCKER_INFO_EXIT:-0}"
fi
exit 0
"""


class Sandbox:
    def __init__(self, cloned: bool = True, docker: bool = True, engine: int = 0) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.checkout = self.folder / "checkout"
        self.bin = self.folder / "bin"
        self.log = self.folder / "docker.log"
        self.checkout.mkdir()
        self.bin.mkdir()
        shutil.copy2(LAUNCHER, self.checkout / "run.sh")
        if cloned:
            (self.checkout / ".git").mkdir()
        if docker:
            fake = self.bin / "docker"
            fake.write_text(FAKE_DOCKER)
            fake.chmod(0o755)
        self.engine = engine

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "PATH": f"{self.bin}:{SYSTEM_PATH}",
            "DOCKER_LOG": str(self.log),
            "DOCKER_INFO_EXIT": str(self.engine),
        }
        return subprocess.run(
            ["sh", str(self.checkout / "run.sh"), *args],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            stdin=subprocess.DEVNULL,
        )

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def close(self) -> None:
        shutil.rmtree(self.folder)


class LauncherRefusesTest(unittest.TestCase):
    def test_a_downloaded_archive_is_refused_with_the_clone_command(self) -> None:
        # Arrange
        box = Sandbox(cloned=False)
        self.addCleanup(box.close)

        # Act
        done = box.run("doctor.py")

        # Assert
        self.assertEqual(done.returncode, 1)
        self.assertIn("downloaded archive", done.stderr)
        self.assertIn(
            "git clone --recurse-submodules "
            "https://github.com/gufranco/snes-dungeon-master-nochip.git",
            done.stderr,
        )

    def test_a_machine_without_docker_is_told_to_install_it(self) -> None:
        # Arrange
        box = Sandbox(docker=False)
        self.addCleanup(box.close)

        # Act
        done = box.run("doctor.py")

        # Assert
        self.assertEqual(done.returncode, 1)
        self.assertIn("Docker is not installed", done.stderr)

    def test_an_engine_that_does_not_answer_is_told_to_start(self) -> None:
        # Arrange
        box = Sandbox(engine=1)
        self.addCleanup(box.close)

        # Act
        done = box.run("doctor.py")

        # Assert
        self.assertEqual(done.returncode, 1)
        self.assertIn("Start Docker Desktop", done.stderr)
        self.assertEqual(box.calls(), ["info"])


class LauncherRunsTest(unittest.TestCase):
    def test_a_script_runs_under_python_in_the_runtime_image(self) -> None:
        # Arrange
        box = Sandbox()
        self.addCleanup(box.close)

        # Act
        done = box.run("pack.py", "usa")

        # Assert
        self.assertEqual(done.returncode, 0, done.stderr)
        build, run = box.calls()[1:]
        self.assertTrue(build.startswith("build --quiet --target runtime"))
        self.assertTrue(run.endswith("snes-dungeon-master-nochip:runtime python3 pack.py usa"))

    def test_the_checkout_is_mounted_without_a_network(self) -> None:
        # Arrange
        box = Sandbox()
        self.addCleanup(box.close)

        # Act
        box.run("doctor.py")

        # Assert
        run = box.calls()[-1]
        self.assertIn(f"--volume {box.checkout}:/work", run)
        self.assertIn("--network none", run)
        self.assertIn(f"--user {os.getuid()}:{os.getgid()}", run)

    def test_the_gates_run_in_their_own_image(self) -> None:
        # Arrange
        box = Sandbox()
        self.addCleanup(box.close)

        # Act
        box.run("--gates")

        # Assert
        build, run = box.calls()[1:]
        self.assertTrue(build.startswith("build --quiet --target gates"))
        self.assertTrue(run.endswith("snes-dungeon-master-nochip:gates sh scripts/gates.sh"))

    def test_a_program_in_the_image_runs_as_named_with_exec(self) -> None:
        # Arrange
        box = Sandbox()
        self.addCleanup(box.close)

        # Act
        box.run("--exec", "dmemu", "build/a.sfc", "600")

        # Assert
        run = box.calls()[-1]
        self.assertTrue(run.endswith("snes-dungeon-master-nochip:runtime dmemu build/a.sfc 600"))

    def test_a_script_after_gates_runs_in_the_gates_image(self) -> None:
        # Arrange
        box = Sandbox()
        self.addCleanup(box.close)

        # Act
        box.run("--gates", "check.py", "--quick")

        # Assert
        run = box.calls()[-1]
        self.assertTrue(run.endswith("snes-dungeon-master-nochip:gates python3 check.py --quick"))


if __name__ == "__main__":
    unittest.main()
