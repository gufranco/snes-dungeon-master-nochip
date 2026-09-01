import importlib.util
import unittest
from collections import namedtuple
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load_module("check", ROOT / "check.py")

Finished = namedtuple("Finished", "returncode stdout stderr")


def answering(codes: dict[str, int]) -> Any:
    """A stand-in for shelling out that fails whichever gates are named."""

    def _run(args: list[str]) -> Any:
        joined = " ".join(args)
        for name, code in codes.items():
            if name in joined:
                return Finished(code, "", f"{name} said no")
        return Finished(0, "", "")

    return _run


class GateTest(unittest.TestCase):
    """What a run is made of."""

    def test_every_gate_names_itself(self) -> None:
        self.assertTrue(all(one.name for one in check.GATES))

    def test_every_gate_pins_the_version_it_runs(self) -> None:
        loose = [
            one.name
            for one in check.GATES
            if any(tool in " ".join(one.command) for tool in ("ruff", "mypy", "coverage"))
            and "==" not in " ".join(one.command)
            and "@" not in " ".join(one.command)
        ]

        self.assertEqual(loose, [])

    def test_the_formatter_runs_over_the_whole_project(self) -> None:
        formatting = [one for one in check.GATES if one.name == "format"]

        self.assertEqual(formatting[0].command[-1], ".")


class RunTest(unittest.TestCase):
    """One pass over the gates."""

    def test_a_clean_run_reports_every_gate_and_passes(self) -> None:
        said: list[str] = []

        code = check.main(["check.py"], said.append, execute=answering({}), ready=lambda **_k: 0)

        self.assertEqual(code, 0)
        for gate in check.GATES:
            self.assertTrue(any(gate.name in one for one in said), gate.name)

    def test_a_failing_gate_is_named_and_the_run_fails(self) -> None:
        said: list[str] = []

        code = check.main(
            ["check.py"], said.append, execute=answering({"mypy": 1}), ready=lambda **_k: 0
        )

        self.assertEqual(code, 1)
        self.assertTrue(any("types" in one and "no" in one for one in said))

    def test_every_gate_runs_even_after_one_fails(self) -> None:
        ran: list[str] = []

        def _run(args: list[str]) -> Any:
            ran.append(args[0])
            return Finished(1, "", "")

        check.main(["check.py"], lambda _l: None, execute=_run, ready=lambda **_k: 0)

        self.assertEqual(len(ran), len(check.GATES))

    def test_what_a_failing_gate_said_is_shown(self) -> None:
        said: list[str] = []

        check.main(
            ["check.py"], said.append, execute=answering({"actionlint": 1}), ready=lambda **_k: 0
        )

        self.assertTrue(any("said no" in one for one in said))


class ImageTest(unittest.TestCase):
    """The image the deeper gates need."""

    def test_a_dump_that_cannot_be_assembled_stops_the_deeper_gates(self) -> None:
        said: list[str] = []

        code = check.main(["check.py"], said.append, execute=answering({}), ready=lambda **_k: 2)

        self.assertEqual(code, 0)
        self.assertTrue(any("skipped" in one for one in said))

    def test_the_deeper_gates_run_when_the_image_is_there(self) -> None:
        ran: list[list[str]] = []

        def _run(args: list[str]) -> Any:
            ran.append(args)
            return Finished(0, "", "")

        check.main(["check.py"], lambda _l: None, execute=_run, ready=lambda **_k: 0)

        self.assertTrue(any("cost.py" in " ".join(one) for one in ran))

    def test_and_are_left_out_when_it_is_not(self) -> None:
        ran: list[list[str]] = []

        def _run(args: list[str]) -> Any:
            ran.append(args)
            return Finished(0, "", "")

        check.main(["check.py"], lambda _l: None, execute=_run, ready=lambda **_k: 2)

        self.assertFalse(any("cost.py" in " ".join(one) for one in ran))


class QuickTest(unittest.TestCase):
    """The pass that leaves out what needs a container."""

    def test_it_runs_none_of_the_gates_that_shell_into_one(self) -> None:
        ran: list[list[str]] = []

        def _run(args: list[str]) -> Any:
            ran.append(args)
            return Finished(0, "", "")

        check.main(["check.py", "--quick"], lambda _l: None, execute=_run, ready=lambda **_k: 0)

        self.assertFalse(any("cost.py" in " ".join(one) for one in ran))

    def test_and_still_runs_the_ones_that_do_not(self) -> None:
        ran: list[list[str]] = []

        def _run(args: list[str]) -> Any:
            ran.append(args)
            return Finished(0, "", "")

        check.main(["check.py", "--quick"], lambda _l: None, execute=_run, ready=lambda **_k: 0)

        self.assertTrue(any("ruff" in " ".join(one) for one in ran))

    def test_a_flag_it_does_not_know_is_refused(self) -> None:
        said: list[str] = []

        code = check.main(["check.py", "--nonsense"], said.append)

        self.assertEqual((code, "usage" in said[0]), (2, True))


class RealShellTest(unittest.TestCase):
    """The path that actually shells out, run against a command that does nothing."""

    def test_it_runs_the_command_and_hands_back_what_it_returned(self) -> None:
        self.assertEqual(check._shell_out(["true"]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
