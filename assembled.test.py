import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assembled = load_module("assembled", ROOT / "assembled.py")


def _kept(seen: list[Any], what: Any) -> int:
    """A stand-in for the builder that keeps what it was asked and succeeds."""
    seen.append(what)
    return 0


def aged(path: Path, when: float) -> None:
    os.utime(path, (when, when))


class WhereTest(unittest.TestCase):
    """What the measurements are pointed at."""

    def test_the_label_table_sits_beside_the_image(self) -> None:
        self.assertEqual(assembled.SYMBOLS, assembled.IMAGE.with_suffix(".sym"))

    def test_the_assembly_it_is_built_from_is_there(self) -> None:
        self.assertTrue(assembled.ASSEMBLY.exists())

    def test_every_source_the_assembler_reads_is_counted(self) -> None:
        found = assembled.sources()

        self.assertIn(assembled.ASSEMBLY, found)
        self.assertGreater(len(found), 1)


class StaleTest(unittest.TestCase):
    """Whether what is on disk can be measured against."""

    def staged(self, tmp: str, image_at: float, symbols_at: float, source_at: float) -> Any:
        where = Path(tmp)
        (where / "asm").mkdir()
        image = where / "asm" / "dm-sym.sfc"
        symbols = where / "asm" / "dm-sym.sym"
        source = where / "asm" / "nochip.asm"
        for one in (source, image, symbols):
            one.write_bytes(b"\x00")
        aged(source, source_at)
        aged(image, image_at)
        aged(symbols, symbols_at)
        assembled.IMAGE = image
        assembled.SYMBOLS = symbols
        assembled.ASSEMBLY = source
        return image

    @override
    def setUp(self) -> None:
        self.kept = (assembled.IMAGE, assembled.SYMBOLS, assembled.ASSEMBLY)

    @override
    def tearDown(self) -> None:
        assembled.IMAGE, assembled.SYMBOLS, assembled.ASSEMBLY = self.kept

    def test_an_image_newer_than_its_sources_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.staged(tmp, image_at=200, symbols_at=200, source_at=100)

            self.assertIsNone(assembled.stale())

    def test_an_image_that_was_never_built_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = self.staged(tmp, image_at=200, symbols_at=200, source_at=100)
            image.unlink()

            self.assertIn("has not been built", str(assembled.stale()))

    def test_a_missing_label_table_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.staged(tmp, image_at=200, symbols_at=200, source_at=100)
            assembled.SYMBOLS.unlink()

            self.assertIn("missing", str(assembled.stale()))

    def test_a_label_table_older_than_its_image_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.staged(tmp, image_at=200, symbols_at=100, source_at=50)

            self.assertIn("older", str(assembled.stale()))

    def test_an_image_older_than_a_source_names_that_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.staged(tmp, image_at=100, symbols_at=100, source_at=200)

            self.assertIn("nochip.asm", str(assembled.stale()))


class AssembleTest(unittest.TestCase):
    """The one call that builds both."""

    def test_a_missing_dump_is_reported_rather_than_assembled(self) -> None:
        said: list[str] = []

        code = assembled.assemble(Path("/nonexistent.sfc"), said.append)

        self.assertEqual((code, "no dump" in said[0]), (2, True))

    def test_it_asks_the_builder_for_the_image_the_measurements_read(self) -> None:
        asked: list[list[str]] = []

        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "dump.sfc"
            dump.write_bytes(b"\x00")

            assembled.assemble(dump, lambda _l: None, lambda argv, **_k: _kept(asked, argv))

        self.assertIn(assembled.IMAGE.name, asked[0])
        self.assertIn(str(assembled.ASSEMBLY), asked[0])

    def test_what_the_builder_returns_is_what_comes_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "dump.sfc"
            dump.write_bytes(b"\x00")

            found = assembled.assemble(dump, lambda _l: None, lambda _argv, **_k: 1)

        self.assertEqual(found, 1)


class ReadyTest(unittest.TestCase):
    """Assembling only when what is there will not do."""

    def test_an_image_that_is_current_is_left_alone(self) -> None:
        asked: list[Any] = []
        kept = (assembled.IMAGE, assembled.SYMBOLS, assembled.ASSEMBLY)

        with tempfile.TemporaryDirectory() as tmp:
            where = Path(tmp)
            (where / "asm").mkdir()
            for name, when in (("nochip.asm", 100), ("dm-sym.sfc", 200), ("dm-sym.sym", 200)):
                (where / "asm" / name).write_bytes(b"\x00")
                aged(where / "asm" / name, when)
            assembled.ASSEMBLY = where / "asm" / "nochip.asm"
            assembled.IMAGE = where / "asm" / "dm-sym.sfc"
            assembled.SYMBOLS = where / "asm" / "dm-sym.sym"
            try:
                code = assembled.ready(
                    assembled.DUMP, lambda _l: None, lambda *_a, **_k: _kept(asked, 1)
                )
            finally:
                assembled.IMAGE, assembled.SYMBOLS, assembled.ASSEMBLY = kept

        self.assertEqual((code, asked), (0, []))

    def test_a_stale_image_is_rebuilt_and_the_reason_said(self) -> None:
        said: list[str] = []
        asked: list[Any] = []

        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "dump.sfc"
            dump.write_bytes(b"\x00")
            kept = assembled.IMAGE
            assembled.IMAGE = Path(tmp) / "absent.sfc"
            try:
                code = assembled.ready(dump, said.append, lambda *_a, **_k: _kept(asked, 1))
            finally:
                assembled.IMAGE = kept

        self.assertEqual((code, len(asked)), (0, 1))
        self.assertIn("has not been built", said[0])


if __name__ == "__main__":
    unittest.main()
