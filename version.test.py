import unittest
from pathlib import Path

import version

ROOT = Path(__file__).resolve().parent


class VersionTest(unittest.TestCase):
    def test_the_version_is_three_numbers(self) -> None:
        parts = version.VERSION.split(".")

        self.assertEqual(len(parts), 3)
        self.assertTrue(all(part.isdigit() for part in parts))

    def test_a_released_build_carries_its_number_and_nothing_else(self) -> None:
        self.assertEqual(version.stamped("dungeon-master", "1.2.3"), "dungeon-master-v1.2.3.sfc")

    def test_an_unreleased_build_says_so_in_its_name(self) -> None:
        stamped = version.stamped("dungeon-master", version.UNRELEASED)

        self.assertEqual(stamped, f"dungeon-master-v{version.UNRELEASED}-dev.sfc")

    def test_the_default_release_is_the_one_the_module_carries(self) -> None:
        self.assertEqual(
            version.stamped("dungeon-master"),
            version.stamped("dungeon-master", version.VERSION),
        )

    def test_every_name_ends_in_the_one_extension(self) -> None:
        self.assertTrue(version.stamped("anything", "9.9.9").endswith(version.EXTENSION))


class ReleaseWiringTest(unittest.TestCase):
    def test_the_release_job_rewrites_the_file_the_build_reads(self) -> None:
        self.assertIn('"version.py"', (ROOT / ".releaserc.json").read_text())

    def test_the_script_that_rewrites_it_points_at_the_same_file(self) -> None:
        self.assertIn("version.py", (ROOT / "scripts" / "set-version.sh").read_text())

    def test_the_script_matches_the_assignment_the_module_actually_uses(self) -> None:
        script = (ROOT / "scripts" / "set-version.sh").read_text()

        self.assertIn('VERSION = "', script)
        self.assertTrue((ROOT / "version.py").read_text().startswith('VERSION = "'))


if __name__ == "__main__":
    unittest.main()
