import importlib.util
import unittest
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).resolve().parent / "script.py"


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("script", MODULE_PATH)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_module()


class EntryTest(unittest.TestCase):
    def test_an_imported_module_runs_nothing(self) -> None:
        # Arrange
        ran: list[tuple[object, ...]] = []

        # Act
        script.entry("tools.identify", lambda *args: ran.append(args))

        # Assert
        self.assertEqual(ran, [])

    def test_a_module_run_as_a_script_exits_with_what_its_main_returned(self) -> None:
        # Arrange
        def main(argv: list[str], verbose: bool) -> int:
            return len(argv) + int(verbose)

        # Act
        with self.assertRaises(SystemExit) as raised:
            script.entry("__main__", main, ["a", "b"], verbose=True)

        # Assert
        self.assertEqual(raised.exception.code, 3)

    def test_a_main_that_returns_nothing_exits_cleanly(self) -> None:
        # Arrange
        def main() -> None:
            return None

        # Act
        with self.assertRaises(SystemExit) as raised:
            script.entry("__main__", main)

        # Assert
        self.assertIsNone(raised.exception.code)


class SkipUnlessTest(unittest.TestCase):
    def test_a_present_input_lets_the_test_go_on(self) -> None:
        # Arrange
        present = Path(__file__)

        # Act
        found = script.skip_unless(present.exists(), "the input is absent")

        # Assert
        self.assertIsNone(found)

    def test_an_absent_input_skips_with_the_reason(self) -> None:
        # Arrange
        absent = Path(__file__).with_name("no-such-dump.sfc")

        # Act
        with self.assertRaises(unittest.SkipTest) as raised:
            script.skip_unless(absent.exists(), "the dump is not here")

        # Assert
        self.assertEqual(str(raised.exception), "the dump is not here")


class NeededTest(unittest.TestCase):
    def test_a_value_that_is_there_comes_back(self) -> None:
        # Arrange
        value = b"\x00\x01"

        # Act
        found = script.needed(value, "the dump is not here")

        # Assert
        self.assertEqual(found, b"\x00\x01")

    def test_a_missing_value_skips_with_the_reason(self) -> None:
        # Arrange
        value = None

        # Act
        with self.assertRaises(unittest.SkipTest) as raised:
            script.needed(value, "the dump is not here")

        # Assert
        self.assertEqual(str(raised.exception), "the dump is not here")


script.entry(__name__, unittest.main)
