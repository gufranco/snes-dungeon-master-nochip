import contextlib
import importlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

external: Any = importlib.import_module("conformance.external")

ABC = {
    "size": 3,
    "crc32": "352441c2",
    "md5": "900150983cd24fb0d6963f7d28e17f72",
    "sha1": "a9993e364706816aba3e25717850c26c9cd0d89d",
    "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
}

OTHER_SHA256 = "ab" * 32


def a_folder(files: dict[str, bytes]) -> Path:
    folder = Path(tempfile.mkdtemp()) / "external"
    for rel, body in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return folder


def an_entry(path: str = "set/abc.bin", **fields: Any) -> dict[str, Any]:
    return {
        "label": "the only release",
        "path": path,
        "common_filename": "abc.bin",
        **ABC,
        **fields,
    }


def an_artifact(*entries: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {"required": False, "accepted": list(entries or [an_entry()]), **fields}


def a_manifest(artifact: dict[str, Any]) -> Path:
    path = Path(tempfile.mkdtemp()) / "artifacts.manifest.json"
    path.write_text(json.dumps({"artifacts": {"boot": {}}, "external": {"abc": artifact}}))
    return path


def a_repository(where: Path) -> str:
    where.mkdir(parents=True)
    (where / "case.json").write_text("[]")
    identity = ["-c", "user.name=a", "-c", "user.email=a@b.c", "-c", "commit.gpgsign=false"]
    for step in (["init", "-q"], ["add", "."], [*identity, "commit", "-q", "-m", "one"]):
        subprocess.run(["git", "-C", str(where), *step], check=True, capture_output=True)
    done = subprocess.run(
        ["git", "-C", str(where), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def a_checkout(commit: str) -> dict[str, Any]:
    return {
        "kind": "checkout",
        "required": False,
        "path": "suites/z80",
        "repository": "https://example.org/suites.git",
        "commit": commit,
        "fetchedBy": "python3 -m conformance.fetch external/suites",
    }


def printed(call: Any) -> tuple[Any, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = call()
    return result, out.getvalue()


class TheManifestTest(unittest.TestCase):
    def test_the_repository_manifest_lists_what_external_holds(self) -> None:
        # Arrange
        manifest = ROOT / "artifacts.manifest.json"

        # Act
        held = external.kept(manifest)

        # Assert
        self.assertIsInstance(held, dict)

    def test_a_manifest_is_read_from_the_path_given(self) -> None:
        # Arrange
        manifest = a_manifest(an_artifact())

        # Act
        held = external.kept(manifest)

        # Assert
        self.assertEqual(list(held), ["abc"])


class IdentityTest(unittest.TestCase):
    def test_every_digest_of_a_known_input_matches_its_published_value(self) -> None:
        # Arrange
        folder = a_folder({"abc.bin": b"abc"})

        # Act
        found = external.identity(folder / "abc.bin")

        # Assert
        self.assertEqual(found, ABC)


class ExamineTest(unittest.TestCase):
    def test_a_file_whose_sha256_matches_is_verified(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abc"})

        # Act
        state, line = external.examine("abc", an_artifact(), folder)

        # Assert
        self.assertEqual((state, line), ("verified", "abc: set/abc.bin, the only release"))

    def test_a_file_that_is_not_there_is_missing_and_named(self) -> None:
        # Arrange
        folder = a_folder({})

        # Act
        state, line = external.examine("abc", an_artifact(), folder)

        # Assert
        self.assertEqual((state, line), ("missing", "abc: none of set/abc.bin is in external/"))

    def test_a_file_of_the_right_size_with_other_bytes_is_called_altered(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abd"})

        # Act
        state, line = external.examine("abc", an_artifact(), folder)

        # Assert
        self.assertEqual(state, "wrong")
        self.assertIn("the right size with other bytes, so altered or patched", line)

    def test_a_file_of_another_size_is_called_another_file(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abcd"})

        # Act
        state, line = external.examine("abc", an_artifact(), folder)

        # Assert
        self.assertEqual(state, "wrong")
        self.assertIn("is 4 bytes with SHA-256", line)
        self.assertIn("where abc.bin is 3 bytes; it is another file", line)

    def test_a_known_bad_copy_is_named_with_its_reason(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abc"})
        bad = {"sha256": ABC["sha256"], "reason": "an overdump"}
        artifact = an_artifact(an_entry(sha256=OTHER_SHA256), known_bad=[bad])

        # Act
        state, line = external.examine("abc", artifact, folder)

        # Assert
        self.assertEqual(state, "wrong")
        self.assertIn("a known bad copy: an overdump", line)

    def test_a_known_bad_list_that_does_not_match_falls_through_to_the_size(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abd"})
        bad = {"sha256": OTHER_SHA256, "reason": "an overdump"}

        # Act
        state, line = external.examine("abc", an_artifact(known_bad=[bad]), folder)

        # Assert
        self.assertEqual(state, "wrong")
        self.assertNotIn("known bad", line)

    def test_a_second_accepted_variant_is_verified_when_the_first_is_wrong(self) -> None:
        # Arrange
        folder = a_folder({"one/abc.bin": b"abd", "two/abc.bin": b"abc"})
        first = an_entry("one/abc.bin")
        second = an_entry("two/abc.bin", label="the revision")

        # Act
        state, line = external.examine("abc", an_artifact(first, second), folder)

        # Assert
        self.assertEqual((state, line), ("verified", "abc: two/abc.bin, the revision"))


class CheckoutTest(unittest.TestCase):
    def test_a_checkout_at_its_pinned_commit_is_verified(self) -> None:
        # Arrange
        folder = a_folder({})
        commit = a_repository(folder / "suites/z80")

        # Act
        state, line = external.examine("z80", a_checkout(commit), folder)

        # Assert
        self.assertEqual((state, line), ("verified", f"z80: suites/z80 at {commit[:12]}"))

    def test_a_checkout_that_is_not_there_is_missing_and_says_how_to_fetch_it(self) -> None:
        # Arrange
        folder = a_folder({})

        # Act
        state, line = external.examine("z80", a_checkout("c" * 40), folder)

        # Assert
        self.assertEqual(state, "missing")
        self.assertIn("fetch it with python3 -m conformance.fetch external/suites", line)

    def test_a_checkout_at_another_commit_is_wrong(self) -> None:
        # Arrange
        folder = a_folder({})
        commit = a_repository(folder / "suites/z80")

        # Act
        state, line = external.examine("z80", a_checkout("c" * 40), folder)

        # Assert
        self.assertEqual(state, "wrong")
        self.assertIn(f"is at {commit}, pinned at {'c' * 40}", line)

    def test_a_folder_that_is_no_repository_is_wrong(self) -> None:
        # Arrange
        folder = a_folder({"suites/z80/case.json": b"[]"})

        # Act
        state, line = external.examine("z80", a_checkout("c" * 40), folder)

        # Assert
        self.assertEqual(state, "wrong")
        self.assertIn("is at no commit", line)

    def test_the_files_inside_a_checkout_are_not_called_unlisted(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abc", "suites/z80/case.json": b"[]"})
        held = {"abc": an_artifact(), "z80": a_checkout("c" * 40)}

        # Act
        extra = external.unlisted(held, folder)

        # Assert
        self.assertEqual(extra, [])


class UnlistedTest(unittest.TestCase):
    def test_a_file_no_entry_names_is_listed_and_finder_metadata_is_not(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abc", "stray.bin": b"x", "set/.DS_Store": b"x"})

        # Act
        extra = external.unlisted({"abc": an_artifact()}, folder)

        # Assert
        self.assertEqual(extra, ["stray.bin"])

    def test_a_folder_that_is_not_there_holds_nothing_unlisted(self) -> None:
        # Arrange
        folder = Path(tempfile.mkdtemp()) / "external"

        # Act
        extra = external.unlisted({"abc": an_artifact()}, folder)

        # Assert
        self.assertEqual(extra, [])


class DescribeTest(unittest.TestCase):
    def test_a_file_inside_the_folder_is_described_by_its_path_there(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abc"})

        # Act
        code, out = printed(
            lambda: external.main(["--describe", str(folder / "set/abc.bin")], folder)
        )

        # Assert
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out), {"path": "set/abc.bin", "common_filename": "abc.bin", **ABC}
        )

    def test_a_file_outside_the_folder_is_described_by_its_full_path(self) -> None:
        # Arrange
        outside = a_folder({"abc.bin": b"abc"}) / "abc.bin"
        folder = a_folder({})

        # Act
        code, out = printed(lambda: external.main(["--describe", str(outside)], folder))

        # Assert
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["path"], outside.resolve().as_posix())

    def test_a_path_that_is_not_a_file_is_refused(self) -> None:
        # Arrange
        folder = a_folder({})

        # Act
        code, out = printed(lambda: external.main(["--describe", str(folder / "none.bin")], folder))

        # Assert
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)


class ReportTest(unittest.TestCase):
    def test_a_folder_holding_every_artifact_passes_and_counts_it(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abc"})
        manifest = a_manifest(an_artifact())

        # Act
        code, out = printed(lambda: external.main([], folder, manifest))

        # Assert
        self.assertEqual(code, 0)
        self.assertIn("1 of 1 verified, 0 missing, 0 wrong, 0 unlisted", out)

    def test_an_optional_artifact_that_is_missing_is_reported_and_passes(self) -> None:
        # Arrange
        folder = a_folder({"stray.bin": b"x"})
        manifest = a_manifest(an_artifact())

        # Act
        code, out = printed(lambda: external.main([], folder, manifest))

        # Assert
        self.assertEqual(code, 0)
        self.assertIn("MISSING abc", out)
        self.assertIn("UNLISTED stray.bin", out)
        self.assertIn("0 of 1 verified, 1 missing, 0 wrong, 1 unlisted", out)

    def test_a_required_artifact_that_is_missing_fails(self) -> None:
        # Arrange
        folder = a_folder({})
        manifest = a_manifest(an_artifact(required=True))

        # Act
        code, _ = printed(lambda: external.main([], folder, manifest))

        # Assert
        self.assertEqual(code, 1)

    def test_a_wrong_file_fails(self) -> None:
        # Arrange
        folder = a_folder({"set/abc.bin": b"abd"})
        manifest = a_manifest(an_artifact())

        # Act
        code, out = printed(lambda: external.main([], folder, manifest))

        # Assert
        self.assertEqual(code, 1)
        self.assertIn("WRONG abc", out)


class UsageTest(unittest.TestCase):
    def test_an_unknown_argument_prints_the_usage(self) -> None:
        # Arrange
        argv = ["--check"]

        # Act
        with self.assertRaises(SystemExit) as raised:
            external.main(argv)

        # Assert
        self.assertEqual(str(raised.exception), external.USAGE)

    def test_describe_with_no_file_prints_the_usage(self) -> None:
        # Arrange
        argv = ["--describe"]

        # Act
        with self.assertRaises(SystemExit) as raised:
            external.main(argv)

        # Assert
        self.assertEqual(str(raised.exception), external.USAGE)


if __name__ == "__main__":
    unittest.main()
