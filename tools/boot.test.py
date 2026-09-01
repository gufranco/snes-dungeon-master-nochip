import importlib.util
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


boot = load_module("boot", ROOT / "tools" / "boot.py")

Finished = namedtuple("Finished", "returncode stdout stderr")

CLEAN = """Map_LoROMMap
ROM title='DUNGEON MASTER' map=20 chipset=00 size=0A sram=05 dsp=0 bytes=1048576
RESULT load=ok frames=8000 delivered=8000 dspevents=0 brightness=78.7264
"""

STILL_A_CHIP = """Map_LoROMMap
ROM title='DUNGEON MASTER' map=20 chipset=05 size=0A sram=05 dsp=2 bytes=1048576
RESULT load=ok frames=8000 delivered=8000 dspevents=22659925 brightness=65.4415
"""

DARK = """Map_LoROMMap
ROM title='DUNGEON MASTER' map=20 chipset=00 size=0A sram=05 dsp=0 bytes=1048576
RESULT load=ok frames=8000 delivered=8000 dspevents=0 brightness=0.0000
"""


class ReadingTest(unittest.TestCase):
    """What the emulator says about a run, as numbers."""

    def test_it_reads_the_coprocessor_the_header_declares(self) -> None:
        self.assertEqual(boot.read(CLEAN)["dsp"], 0)

    def test_and_the_one_a_retail_header_declares(self) -> None:
        self.assertEqual(boot.read(STILL_A_CHIP)["dsp"], 2)

    def test_it_reads_how_many_times_a_chip_was_asked(self) -> None:
        self.assertEqual(boot.read(STILL_A_CHIP)["dspevents"], 22659925)

    def test_it_reads_how_lit_the_screen_ended_up(self) -> None:
        self.assertAlmostEqual(boot.read(CLEAN)["brightness"], 78.7264)

    def test_it_reads_how_many_frames_were_delivered(self) -> None:
        self.assertEqual(boot.read(CLEAN)["delivered"], 8000)

    def test_output_with_no_result_line_reads_as_nothing(self) -> None:
        self.assertEqual(boot.read("Map_LoROMMap\n"), {})


class VerdictTest(unittest.TestCase):
    """Whether a run is one this project can stand behind."""

    def test_a_clean_run_has_nothing_to_report(self) -> None:
        self.assertEqual(boot.faults(boot.read(CLEAN), 8000), [])

    def test_a_header_still_declaring_a_chip_is_a_fault(self) -> None:
        found = boot.faults(boot.read(STILL_A_CHIP), 8000)

        self.assertTrue(any("declares" in line for line in found))

    def test_a_run_that_asked_a_chip_for_anything_is_a_fault(self) -> None:
        found = boot.faults(boot.read(STILL_A_CHIP), 8000)

        self.assertTrue(any("22,659,925" in line for line in found))

    def test_a_screen_that_never_lit_is_a_fault(self) -> None:
        found = boot.faults(boot.read(DARK), 8000)

        self.assertTrue(any("dark" in line for line in found))

    def test_a_run_cut_short_is_a_fault(self) -> None:
        found = boot.faults(boot.read(CLEAN), 9000)

        self.assertTrue(any("8,000 of 9,000" in line for line in found))

    def test_a_run_that_said_nothing_is_a_fault(self) -> None:
        found = boot.faults({}, 8000)

        self.assertTrue(any("said nothing" in line for line in found))


class CommandTest(unittest.TestCase):
    """The command line."""

    def test_a_missing_cartridge_is_reported_rather_than_run(self) -> None:
        said: list[str] = []

        code = boot.main(["boot.py", "/nonexistent.sfc"], said.append)

        self.assertEqual((code, "build it first" in said[0]), (2, True))

    def test_a_clean_run_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cartridge = Path(tmp) / "dm.sfc"
            cartridge.write_bytes(b"\x00")
            said: list[str] = []

            code = boot.main(
                ["boot.py", str(cartridge), "8000"],
                said.append,
                execute=lambda _a: Finished(0, CLEAN, ""),
            )

        self.assertEqual((code, any("no coprocessor" in line for line in said)), (0, True))

    def test_a_run_that_still_wanted_a_chip_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cartridge = Path(tmp) / "dm.sfc"
            cartridge.write_bytes(b"\x00")
            said: list[str] = []

            code = boot.main(
                ["boot.py", str(cartridge), "8000"],
                said.append,
                execute=lambda _a: Finished(0, STILL_A_CHIP, ""),
            )

        self.assertEqual(code, 1)

    def test_an_emulator_that_did_not_run_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cartridge = Path(tmp) / "dm.sfc"
            cartridge.write_bytes(b"\x00")
            said: list[str] = []

            code = boot.main(
                ["boot.py", str(cartridge), "8000"],
                said.append,
                execute=lambda _a: Finished(1, "", "the container died"),
            )

        self.assertEqual((code, "the container died" in "\n".join(said)), (1, True))


class RealShellTest(unittest.TestCase):
    """The path that actually shells out, run against a command that does nothing."""

    def test_it_runs_the_command_and_hands_back_what_it_returned(self) -> None:
        found = boot._shell_out(["true"])

        self.assertEqual(found.returncode, 0)


class ShellingOutTest(unittest.TestCase):
    """The command that reaches the emulator."""

    def test_it_runs_without_network(self) -> None:
        args = boot.run_command(Path("/w"), "dm.sfc", 8000)

        self.assertIn("--network=none", args)

    def test_it_names_the_pinned_image(self) -> None:
        args = boot.run_command(Path("/w"), "dm.sfc", 8000)

        self.assertIn(boot.EMULATOR, args)
        self.assertNotIn(":latest", boot.EMULATOR)

    def test_it_passes_the_cartridge_by_name_rather_than_by_host_path(self) -> None:
        args = boot.run_command(Path("/some/host"), "dm.sfc", 8000)

        self.assertIn("dm.sfc", args)
        self.assertNotIn("/some/host/dm.sfc", args)

    def test_a_relative_directory_is_resolved_before_it_is_mounted(self) -> None:
        args = boot.run_command(Path("build"), "dm.sfc", 8000)

        mounted = args[args.index("-v") + 1]

        self.assertTrue(mounted.startswith("/"))


if __name__ == "__main__":
    unittest.main()
