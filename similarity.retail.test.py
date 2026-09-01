import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any, override

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assembled = load_module("assembled", ROOT / "assembled.py")
cartridge = load_module("cartridge", ROOT / "cartridge.py")
patch = load_module("patch", ROOT / "patch.py")
similarity = load_module("similarity", ROOT / "similarity.py")


class SimilarityTest(unittest.TestCase):
    """What the cartridge somebody plays keeps of the dump it came from.

    The patch has its own check that it stays inside the instructions it names,
    and it passes. This runs against the other end: the image after the routines
    are placed, the accesses redirected and the header rewritten, which is three
    steps further on and is the thing that reaches a player.
    """

    @override
    def setUp(self) -> None:
        reason = assembled.stale()
        if reason is not None:
            self.skipTest(reason)
        if not assembled.DUMP.exists():
            self.skipTest("the dump this is measured against is not here")

        self.retail = assembled.DUMP.read_bytes()
        self.final = cartridge.finish(assembled.IMAGE.read_bytes(), assembled.SYMBOLS.read_text())
        self.report = similarity.account(
            self.retail,
            self.final,
            assembled.ASSEMBLY.read_text(),
            patch.read_symbols(assembled.SYMBOLS.read_text()),
        )

    def test_every_byte_that_moved_belongs_to_a_declared_region(self) -> None:
        found = similarity.explain(self.report, self.retail, self.final)

        self.assertEqual(self.report.loose, [], found)

    def test_the_cartridge_is_the_size_of_the_dump(self) -> None:
        self.assertEqual(len(self.final), len(self.retail))

    def test_something_did_move(self) -> None:
        self.assertGreater(self.report.differ, 0)

    def test_every_declared_region_carries_some_of_it(self) -> None:
        empty = [
            name
            for name in similarity.claims(
                self.retail,
                assembled.ASSEMBLY.read_text(),
                patch.read_symbols(assembled.SYMBOLS.read_text()),
            )
            if not self.report.counted.get(name)
        ]

        self.assertEqual(empty, [])

    def test_the_retail_code_outside_those_regions_is_byte_for_byte(self) -> None:
        entitled = set()
        for where in similarity.claims(
            self.retail,
            assembled.ASSEMBLY.read_text(),
            patch.read_symbols(assembled.SYMBOLS.read_text()),
        ).values():
            entitled |= where

        kept = all(
            self.retail[at] == self.final[at]
            for at in range(len(self.retail))
            if at not in entitled
        )
        self.assertTrue(kept)


if __name__ == "__main__":
    unittest.main()
