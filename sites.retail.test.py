import importlib.util
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sites = load_module("sites", ROOT / "sites.py")

RETAIL = ROOT / "roms" / "dungeon-master-usa.sfc"


def image_with(pieces):
    end = max((offset + len(payload) for offset, payload in pieces.items()), default=0)
    image = bytearray(max(0x10000, end))
    for offset, payload in pieces.items():
        image[offset : offset + len(payload)] = payload
    return bytes(image)


"""The checks that need the cartridge itself.

Nobody may distribute that dump, so on a machine without it every one of
these reports as skipped. They live apart from the rest because a coverage
gate cannot be met by a file whose paths depend on what a machine holds:
one machine runs these and another runs none of them, and no single build
can exercise both.
"""


@unittest.skipUnless(RETAIL.exists(), "the retail dump is supplied by the builder")
class RetailTest(unittest.TestCase):
    def setUp(self) -> None:
        self.image = RETAIL.read_bytes()

    def test_the_measured_surface_is_the_one_the_dump_carries(self) -> None:
        counted = sites.verify(sites.find(self.image))

        self.assertEqual(
            counted,
            {
                sites.KIND_WRITE: 51,
                sites.KIND_READ: 4,
                sites.KIND_STATUS: 5,
                sites.KIND_FEED: 16,
                sites.KIND_DRAIN: 2,
            },
        )

    def test_every_site_lives_in_the_two_banks_that_drive_the_chip(self) -> None:
        self.assertEqual(sites.banks_touched(sites.find(self.image)), [0x00, 0x04])

    def test_the_status_polls_sit_where_they_were_measured(self) -> None:
        found = sites.find(self.image, [sites.KIND_STATUS])

        self.assertEqual(
            [(site.bank, site.address) for site in found],
            [(0x00, 0x9887), (0x04, 0x84E3), (0x04, 0x8898), (0x04, 0x9775), (0x04, 0x9886)],
        )

    def test_the_port_reads_sit_where_they_were_measured(self) -> None:
        found = sites.find(self.image, [sites.KIND_READ])

        self.assertEqual([site.address for site in found], [0x86D3, 0x86D8, 0x86DE, 0x86E2])

    def test_the_dump_carries_the_measured_trampoline_calls(self) -> None:
        counted = sites.verify_trampoline_calls(sites.find_trampoline_calls(self.image))

        self.assertEqual(counted, {0x0080: 2, 0x0084: 5, 0x0088: 4, 0x008C: 1})

    def test_every_trampoline_call_that_can_reach_the_chip_is_in_one_bank(self) -> None:
        found = sites.find_trampoline_calls(self.image)

        self.assertEqual({site.bank for site in found}, {0x04})


if __name__ == "__main__":
    unittest.main()
