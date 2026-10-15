import json
import sys
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCUMENT = ROOT / "OPEN-QUESTIONS.md"

RECORD = ROOT / "conformance" / "divergences.json"

STATUSES = ("open", "narrowed", "acknowledged", "closed", "notADisagreement", "notModelled")

SEVERITIES = ("contradiction", "high", "medium", "low", "unstated", "unchecked", "outOfScope")

FOLLOWS = ("document", "reference", "recording", "corpus", "cartridges", "microcode", "neither")

SECTIONS_THAT_ARE_NOT_ENTRIES = (
    "What is closed, and why it is worth saying",
    "Boundaries, so nobody mistakes them for gaps",
)

LIVE = ("open", "narrowed", "acknowledged")


def held() -> dict[str, Any]:
    found: dict[str, Any] = json.loads(RECORD.read_text())
    return found


def divergences() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = held()["divergences"]
    return found


def live() -> list[dict[str, Any]]:
    return [one for one in divergences() if one["status"] in LIVE]


class RecordTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.text = DOCUMENT.read_text()

    def test_the_record_says_where_its_facts_came_from(self) -> None:
        self.assertTrue(held()["sources"])

    def test_every_entry_has_an_identifier_of_its_own(self) -> None:
        names = [one["id"] for one in divergences()]

        self.assertEqual(len(names), len(set(names)))

    def test_every_status_is_one_the_family_uses(self) -> None:
        stray = [one["id"] for one in divergences() if one["status"] not in STATUSES]

        self.assertEqual(stray, [])

    def test_every_severity_is_one_the_family_uses(self) -> None:
        stray = [one["id"] for one in divergences() if one["severity"] not in SEVERITIES]

        self.assertEqual(stray, [])

    def test_every_entry_says_what_this_package_followed(self) -> None:
        stray = [one["id"] for one in divergences() if one["packageFollows"] not in FOLLOWS]

        self.assertEqual(stray, [])

    def test_every_entry_names_the_part_it_is_about(self) -> None:
        silent = [one["id"] for one in divergences() if not one.get("parts")]

        self.assertEqual(silent, [])

    def test_every_entry_gives_its_reasoning(self) -> None:
        silent = [one["id"] for one in divergences() if not one.get("reasoning")]

        self.assertEqual(silent, [])

    def test_the_document_names_every_live_entry(self) -> None:
        missing = [one["id"] for one in live() if one["namedInDocument"] not in self.text]

        self.assertEqual(missing, [])

    def test_the_document_holds_no_section_the_record_has_never_heard_of(self) -> None:
        headings = [
            one[3:].strip()
            for one in self.text.splitlines()
            if one.startswith("## ") and one[3:].strip() not in SECTIONS_THAT_ARE_NOT_ENTRIES
        ]
        named = {one["namedInDocument"] for one in divergences()}

        self.assertEqual([one for one in headings if one not in named], [])

    def test_every_entry_names_itself_in_the_document_including_the_settled_ones(self) -> None:
        missing = [one["id"] for one in divergences() if one["namedInDocument"] not in self.text]

        self.assertEqual(missing, [])

    def test_each_live_entry_says_what_measurement_would_close_it(self) -> None:
        silent = [
            one["id"]
            for one in live()
            if not one.get("wouldSettleIt") or one["wouldSettleIt"].startswith("n/a")
        ]

        self.assertEqual(silent, [])

    def test_a_boundary_says_it_is_a_boundary_rather_than_an_unknown(self) -> None:
        wrong = [
            one["id"]
            for one in divergences()
            if one["status"] in ("notADisagreement", "notModelled")
            and not one["wouldSettleIt"].startswith("n/a")
        ]

        self.assertEqual(wrong, [])

    def test_the_closed_ones_are_kept_rather_than_deleted(self) -> None:
        closed = [one for one in divergences() if one["status"] == "closed"]

        self.assertGreater(len(closed), 0)

    def test_a_closed_entry_still_says_what_settled_it(self) -> None:
        silent = [
            one["id"]
            for one in divergences()
            if one["status"] == "closed" and not one.get("reasoning")
        ]

        self.assertEqual(silent, [])

    def test_there_are_live_questions_to_report(self) -> None:
        self.assertEqual(len(live()), 5)

    def test_the_document_separates_boundaries_from_unknowns(self) -> None:
        self.assertIn("Boundaries, so nobody mistakes them for gaps", self.text)

    def test_and_says_what_has_been_closed(self) -> None:
        self.assertIn("What is closed, and why it is worth saying", self.text)

    def test_the_document_points_at_the_record(self) -> None:
        self.assertIn("conformance/divergences.json", self.text)

    def test_no_entry_carries_bytes_of_anything(self) -> None:
        text = json.dumps(held())

        self.assertNotIn("base64", text.lower())


if __name__ == "__main__":
    unittest.main()
