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


placement = load_module("placement", ROOT / "tools" / "placement.py")

Finished = namedtuple("Finished", "returncode stdout stderr")


def mapped(touched: dict[int, int], size: int = 0x20000) -> bytes:
    out = bytearray(b"\x01" * size)
    for at in range(placement.STATE, placement.STATE_END):
        out[at] = 0
    for at, value in touched.items():
        out[at] = value
    return bytes(out)


class BlockTest(unittest.TestCase):
    """Where the state block lives, read from the assembly rather than repeated."""

    def test_it_reads_the_base_the_assembler_declares(self) -> None:
        self.assertEqual(placement.STATE, 0x0900)

    def test_and_the_end_the_assembler_declares(self) -> None:
        self.assertEqual(placement.STATE_END, 0x0F00)

    def test_a_name_the_assembler_does_not_declare_is_refused(self) -> None:
        with self.assertRaises(AssertionError):
            placement.define("!NOT_A_DEFINE", ROOT / "asm" / "dsp2-state.asm")


class ReadingTest(unittest.TestCase):
    """What the map says about the region the block wants."""

    def test_an_untouched_region_reports_nothing_taken(self) -> None:
        self.assertEqual(placement.taken(mapped({})), [])

    def test_a_byte_the_game_wrote_is_reported_with_its_address(self) -> None:
        found = placement.taken(mapped({0x0A00: 1}))

        self.assertEqual(found, [0x0A00])

    def test_a_byte_outside_the_block_is_not_its_business(self) -> None:
        self.assertEqual(placement.taken(mapped({0x0800: 1})), [])


class RunsTest(unittest.TestCase):
    """The stretches of work RAM the game left alone."""

    def test_it_finds_the_longest_stretch(self) -> None:
        found = placement.free(bytes([1, 0, 0, 0, 1, 0, 1]))

        self.assertEqual(found[0], (1, 3))

    def test_a_stretch_that_reaches_the_end_is_counted(self) -> None:
        found = placement.free(bytes([1, 0, 0]))

        self.assertEqual(found[0], (1, 2))

    def test_a_map_with_nothing_free_has_no_stretches(self) -> None:
        self.assertEqual(placement.free(bytes([1, 1])), [])


class VerdictTest(unittest.TestCase):
    """What the run adds up to."""

    def test_a_clear_region_says_so(self) -> None:
        found = placement.summary([], [(0x083E, 4078)], 19000)

        self.assertIn("never touched", found)

    def test_a_region_the_game_uses_names_the_first_byte(self) -> None:
        found = placement.summary([0x0A00, 0x0A01], [(0x083E, 4078)], 19000)

        self.assertIn("$00A00", found)

    def test_it_reports_the_longest_stretch_that_was_free(self) -> None:
        found = placement.summary([], [(0x083E, 4078)], 19000)

        self.assertIn("4,078", found)

    def test_a_map_with_no_free_stretch_at_all_still_reads(self) -> None:
        self.assertIn("none", placement.summary([], [], 19000))


class CommandTest(unittest.TestCase):
    """The command line."""

    def test_a_missing_cartridge_is_reported_rather_than_run(self) -> None:
        said: list[str] = []

        code = placement.main(["placement.py", "/nonexistent.sfc"], said.append)

        self.assertEqual((code, "no dump" in said[0]), (2, True))

    def test_a_run_that_left_the_region_alone_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            cartridge = where / "dm.sfc"
            cartridge.write_bytes(b"\x00")

            def _run(_args: Any) -> Any:
                (where / placement.MAP).write_bytes(mapped({}))
                return Finished(0, "", "")

            said: list[str] = []

            code = placement.main(
                ["placement.py", str(cartridge), "100"], said.append, execute=_run
            )

        self.assertEqual((code, "never touched" in "\n".join(said)), (0, True))

    def test_a_run_that_used_the_region_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            cartridge = where / "dm.sfc"
            cartridge.write_bytes(b"\x00")

            def _run(_args: Any) -> Any:
                (where / placement.MAP).write_bytes(mapped({0x0A00: 1}))
                return Finished(0, "", "")

            said: list[str] = []

            code = placement.main(
                ["placement.py", str(cartridge), "100"], said.append, execute=_run
            )

        self.assertEqual(code, 1)

    def test_an_emulator_that_did_not_run_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cartridge = Path(tmp) / "dm.sfc"
            cartridge.write_bytes(b"\x00")
            said: list[str] = []

            code = placement.main(
                ["placement.py", str(cartridge), "100"],
                said.append,
                execute=lambda _a: Finished(1, "", "the container died"),
            )

        self.assertEqual((code, "did not run" in "\n".join(said)), (1, True))

    def test_a_run_that_left_no_map_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cartridge = Path(tmp) / "dm.sfc"
            cartridge.write_bytes(b"\x00")
            said: list[str] = []

            code = placement.main(
                ["placement.py", str(cartridge), "100"],
                said.append,
                execute=lambda _a: Finished(0, "", ""),
            )

        self.assertEqual((code, "no map" in "\n".join(said)), (1, True))


class RealShellTest(unittest.TestCase):
    """The path that actually shells out, run against a command that does nothing."""

    def test_it_runs_the_command_and_hands_back_what_it_returned(self) -> None:
        self.assertEqual(placement._shell_out(["true"]).returncode, 0)


class ShellingOutTest(unittest.TestCase):
    """The command that reaches the emulator."""

    def test_it_asks_for_the_map(self) -> None:
        args = placement.run_command(Path("/w"), "dm.sfc", 100)

        self.assertIn(f"DMWRAM={placement.MAP}", args)

    def test_it_runs_without_network(self) -> None:
        args = placement.run_command(Path("/w"), "dm.sfc", 100)

        self.assertIn("--network=none", args)

    def test_a_relative_directory_is_resolved_before_it_is_mounted(self) -> None:
        args = placement.run_command(Path("build"), "dm.sfc", 100)

        self.assertTrue(args[args.index("-v") + 1].startswith("/"))


class RouteTest(unittest.TestCase):
    def test_without_a_seed_the_steady_route_is_walked(self) -> None:
        self.assertEqual(placement.route_for(4000, None), placement.tour.steady(4000))

    def test_a_seed_asks_for_a_walk_instead(self) -> None:
        self.assertEqual(placement.route_for(4000, 3), placement.tour.build(4000, 3))

    def test_two_seeds_give_two_different_routes(self) -> None:
        self.assertNotEqual(placement.route_for(4000, 1), placement.route_for(4000, 2))

    def test_a_walk_is_not_the_steady_route(self) -> None:
        self.assertNotEqual(placement.route_for(4000, 1), placement.route_for(4000, None))


if __name__ == "__main__":
    unittest.main()
