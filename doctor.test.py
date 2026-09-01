import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import Any

import doctor
import hardware


class Complaint(Exception):
    pass


def a_finding(
    name: Any = "something",
    ok: Any = True,
    detail: Any = "detail",
    advice: Any = None,
) -> Any:
    return doctor.Finding(name, ok, detail, advice)


class FindingTest(unittest.TestCase):
    def test_a_finding_says_what_was_checked(self) -> None:
        self.assertEqual(a_finding(name="the cartridge").name, "the cartridge")

    def test_and_whether_it_was_well(self) -> None:
        self.assertTrue(a_finding(ok=True).ok)
        self.assertFalse(a_finding(ok=False).ok)

    def test_a_healthy_finding_prints_with_a_mark_that_says_so(self) -> None:
        self.assertIn("ok", a_finding(ok=True).line)

    def test_and_an_unhealthy_one_prints_differently(self) -> None:
        self.assertNotIn("ok", a_finding(ok=False).line)

    def test_every_finding_carries_what_it_actually_saw(self) -> None:
        self.assertIn("1048576 bytes", a_finding(detail="1048576 bytes").line)

    def test_an_unhealthy_finding_says_what_to_do_about_it(self) -> None:
        self.assertIn("go and look", a_finding(ok=False, advice="go and look").report)

    def test_a_healthy_one_carries_no_advice(self) -> None:
        self.assertEqual(a_finding(ok=True, advice="x").report, a_finding(ok=True).line)

    def test_a_finding_prints_as_itself(self) -> None:
        self.assertIn("something", repr(a_finding()))


class ExamineTest(unittest.TestCase):
    def test_the_examination_produces_findings(self) -> None:
        self.assertTrue(doctor.examine())

    def test_it_reports_the_python_it_is_running_on(self) -> None:
        self.assertIn("python", [one.name for one in doctor.examine()])

    def test_and_the_version_of_this_project(self) -> None:
        self.assertIn("snes-dungeon-master-nochip", [one.name for one in doctor.examine()])

    def test_every_finding_carries_a_detail(self) -> None:
        for one in doctor.examine():
            self.assertTrue(one.detail, one.name)


class ModelTest(unittest.TestCase):
    def test_every_model_this_project_is_built_on_is_reported(self) -> None:
        import hardware

        names = [one.name for one in doctor.examine()]

        for package in hardware.PACKAGES:
            self.assertTrue(any(package in name for name in names), package)

    def test_a_model_that_is_not_checked_out_is_a_failure(self) -> None:
        found = doctor._model("mos65xx", Path("/nowhere/at/all"), lambda _name: None)

        self.assertFalse(found.ok)
        self.assertIn("submodule", found.advice)

    def test_a_model_that_will_not_import_is_reported_as_what_it_threw(self) -> None:
        def boom(_name: Any) -> None:
            raise Complaint("the model exploded")

        where = Path(tempfile.mkdtemp())
        (where / "something").write_text("here")

        found = doctor._model("mos65xx", where, boom)

        self.assertFalse(found.ok)
        self.assertIn("the model exploded", found.detail)
        self.assertIn("Complaint", found.detail)

    def test_a_model_that_imports_is_reported_with_its_version(self) -> None:
        where = Path(tempfile.mkdtemp())
        (where / "something").write_text("here")

        found = doctor._model("mos65xx", where, lambda _name: type("M", (), {"VERSION": "9.9.9"}))

        self.assertTrue(found.ok)
        self.assertIn("9.9.9", found.detail)


class MicrocodeTest(unittest.TestCase):
    def test_the_report_says_whether_the_part_can_run(self) -> None:
        self.assertIn("microcode", [one.name for one in doctor.examine()])

    def test_a_machine_with_none_is_a_failure_that_says_where_to_put_it(self) -> None:
        found = doctor._microcode(lambda: "no image is here", lambda: [])

        self.assertFalse(found.ok)
        self.assertIn("firmware", found.advice)

    def test_and_carries_what_the_part_itself_said(self) -> None:
        found = doctor._microcode(lambda: "no image is here", lambda: [])

        self.assertIn("no image is here", found.detail)

    def test_a_machine_with_one_says_which_parts_it_can_run(self) -> None:
        found = doctor._microcode(lambda: None, lambda: ["dsp2"])

        self.assertTrue(found.ok)
        self.assertIn("dsp2", found.detail)

    def test_a_part_that_throws_when_asked_is_reported_rather_than_swallowed(self) -> None:
        def boom() -> None:
            raise Complaint("the part exploded")

        found = doctor._microcode(boom, lambda: [])

        self.assertFalse(found.ok)
        self.assertIn("the part exploded", found.detail)


class CartridgeTest(unittest.TestCase):
    def test_the_report_says_whether_the_cartridge_is_here(self) -> None:
        names = " ".join(one.name for one in doctor.examine())

        self.assertIn("cartridge", names)

    def test_a_cartridge_that_is_here_is_reported_with_its_digest(self) -> None:
        found = doctor._cartridges(
            lambda: [
                doctor.identify.Finding(
                    "Dungeon Master, USA",
                    "dungeon-master-usa.sfc",
                    doctor.identify.STATE_OK,
                    "",
                    doctor.identify.Identity(1, "a", "b", "c", "abc123"),
                    "bare",
                )
            ]
        )

        self.assertTrue(found[0].ok)
        self.assertIn("abc123", found[0].detail)

    def test_one_that_is_absent_is_reported_without_pretending_otherwise(self) -> None:
        found = doctor._cartridges(
            lambda: [
                doctor.identify.Finding(
                    "Dungeon Master, USA",
                    "dungeon-master-usa.sfc",
                    doctor.identify.STATE_MISSING,
                    "roms/dungeon-master-usa.sfc is not there",
                    None,
                    None,
                )
            ]
        )

        self.assertFalse(found[0].ok)
        self.assertIn("not there", found[0].detail)

    def test_a_check_that_throws_is_reported_rather_than_swallowed(self) -> None:
        def boom() -> None:
            raise Complaint("no manifest at all")

        found = doctor._cartridges(boom)

        self.assertFalse(found[0].ok)
        self.assertIn("no manifest at all", found[0].detail)


class BeneathTest(unittest.TestCase):
    """That what this is built on is examined too, and under its own name."""

    def test_the_models_that_carry_a_doctor_are_asked_for_theirs(self) -> Any:
        def beneath() -> Any:
            return [("snes-dsp-python", doctor.Finding("python", True, "some version"))]

        for one in doctor.examine(beneath=beneath):
            if one.name.startswith("snes-dsp-python /"):
                self.assertIn("/", one.name)

    def test_a_model_that_cannot_be_asked_is_reported_like_an_absent_one(self) -> None:
        def beneath() -> None:
            raise Complaint("no doctor down there")

        found = doctor.examine(beneath=beneath)

        text = "\n".join(one.report for one in found)
        self.assertIn("no doctor down there", text)
        self.assertIn("Complaint", text)

    def test_an_unwell_finding_beneath_makes_this_run_unwell_too(self) -> Any:
        def beneath() -> Any:
            return [("snes-dsp-python", doctor.Finding("something", False, "not well", "look"))]

        self.assertTrue(any(not one.ok for one in doctor.examine(beneath=beneath)))

    def test_nothing_underneath_at_all_is_not_a_failure(self) -> None:
        found = doctor.examine(beneath=list)

        self.assertTrue(all(one.ok for one in found if " / " in one.name))


class AskingEachTest(unittest.TestCase):
    """Which models get asked for a report, and which are passed over."""

    def _a_doctor(self, findings: Any) -> Any:
        return type("Underneath", (), {"examine": staticmethod(lambda: findings)})

    def test_a_model_that_is_not_checked_out_is_passed_over(self) -> None:
        found = doctor._ask_each(["nothing"], lambda _name: "/nowhere/at/all", lambda _n: None)

        self.assertEqual(found, [])

    def test_a_model_with_no_doctor_is_passed_over_too(self) -> None:
        def absent(_name: Any) -> None:
            raise ModuleNotFoundError("no doctor there")

        found = doctor._ask_each(["mos65xx"], hardware.root_of, absent)

        self.assertEqual(found, [])

    def test_a_model_whose_doctor_will_not_run_is_left_to_raise(self) -> None:
        def broken(_name: Any) -> None:
            raise Complaint("the doctor there exploded")

        with self.assertRaises(Complaint):
            doctor._ask_each(["mos65xx"], hardware.root_of, broken)

    def test_a_model_not_yet_on_the_import_path_is_put_there(self) -> None:
        where = Path(tempfile.mkdtemp())
        (where / "something").write_text("here")
        self.addCleanup(lambda: sys.path.remove(str(where)) if str(where) in sys.path else None)

        doctor._ask_each(["made-up"], lambda _name: where, lambda _name: self._a_doctor([]))

        self.assertIn(str(where), sys.path)

    def test_what_a_model_reports_comes_back_under_its_directory_name(self) -> None:
        finding = doctor.Finding("python", True, "some version")

        found = doctor._ask_each(
            ["mos65xx"], hardware.root_of, lambda _name: self._a_doctor([finding])
        )

        self.assertEqual(found, [("mos65xx-python", finding)])


class UnusedTest(unittest.TestCase):
    def test_the_parts_this_cartridge_does_not_carry_are_named(self) -> None:
        found = doctor._default_unused(lambda _name: type("M", (), {"MODELS": {"dsp1", "dsp2"}}))

        self.assertEqual(found, ["dsp1"])

    def test_a_model_that_will_not_import_leaves_every_finding_standing(self) -> None:
        def boom(_name: Any) -> None:
            raise Complaint("no model at all")

        self.assertEqual(doctor._default_unused(boom), [])


class ReportTest(unittest.TestCase):
    def test_the_report_has_a_line_for_every_finding(self) -> None:
        found = doctor.examine()

        self.assertGreaterEqual(len(doctor.report(found)), len(found))

    def test_it_opens_with_something_that_says_what_it_is(self) -> None:
        self.assertIn("snes-dungeon-master-nochip", doctor.report(doctor.examine())[0])

    def test_an_unhealthy_run_says_how_many_did_not_pass(self) -> None:
        self.assertIn("1", " ".join(doctor.report([a_finding(ok=False)])))

    def test_a_healthy_run_says_there_is_nothing_to_report(self) -> None:
        self.assertIn("nothing to report", " ".join(doctor.report([a_finding(ok=True)])))


class EntryTest(unittest.TestCase):
    def test_a_healthy_run_reports_success(self) -> None:
        self.assertEqual(
            doctor.main([], examine=lambda **_: [a_finding(ok=True)], say=lambda _: None), 0
        )

    def test_an_unhealthy_one_reports_failure(self) -> None:
        self.assertEqual(
            doctor.main([], examine=lambda **_: [a_finding(ok=False)], say=lambda _: None), 1
        )

    def test_the_report_is_printed_rather_than_kept(self) -> None:
        said: list[Any] = []

        doctor.main([], examine=lambda **_: [a_finding(ok=True)], say=said.append)

        self.assertTrue(said)

    def test_a_real_run_says_something_about_this_machine(self) -> None:
        said: list[Any] = []

        doctor.main([], say=said.append)

        self.assertIn("snes-dungeon-master-nochip", " ".join(said))


if __name__ == "__main__":
    unittest.main()
