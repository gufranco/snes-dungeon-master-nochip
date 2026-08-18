import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
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


class AddressTest(unittest.TestCase):
    def test_the_first_bank_starts_at_the_window(self):
        self.assertEqual(sites.address_of(0), (0, 0x8000))

    def test_an_offset_maps_to_the_bank_that_holds_it(self):
        self.assertEqual(sites.address_of(0x20000), (4, 0x8000))

    def test_an_address_and_an_offset_are_inverses(self):
        for offset in (0, 1, 0x7FFF, 0x8000, 0x20123, 0xFFFFF):
            bank, address = sites.address_of(offset)

            self.assertEqual(sites.offset_of(bank, address), offset)

    def test_a_mirrored_bank_reads_the_same_offset(self):
        self.assertEqual(sites.offset_of(0x80, 0x8000), sites.offset_of(0x00, 0x8000))


class ScanTest(unittest.TestCase):
    def test_a_pattern_that_is_absent_is_not_found(self):
        self.assertEqual(sites.occurrences(bytes(64), b"\x8f\x00\x80\x3f"), [])

    def test_every_occurrence_is_reported(self):
        image = image_with({0x10: sites.STA_PORT, 0x400: sites.STA_PORT})

        self.assertEqual(sites.occurrences(image, sites.STA_PORT), [0x10, 0x400])

    def test_overlapping_occurrences_are_not_skipped(self):
        pattern = b"\xaa\xaa"

        self.assertEqual(sites.occurrences(b"\xaa\xaa\xaa", pattern), [0, 1])


class FindTest(unittest.TestCase):
    def test_each_kind_is_recognised_by_its_own_bytes(self):
        image = image_with(
            {
                0x100: sites.STA_PORT,
                0x200: sites.LDA_PORT,
                0x300: sites.LDA_STATUS,
                0x400: sites.MVN_TO_PORT,
                0x500: sites.MVN_FROM_PORT,
            }
        )

        found = {site.kind: site.offset for site in sites.find(image)}

        self.assertEqual(
            found,
            {
                sites.KIND_WRITE: 0x100,
                sites.KIND_READ: 0x200,
                sites.KIND_STATUS: 0x300,
                sites.KIND_FEED: 0x400,
                sites.KIND_DRAIN: 0x500,
            },
        )

    def test_sites_come_back_in_file_order(self):
        image = image_with({0x500: sites.STA_PORT, 0x100: sites.LDA_PORT})

        self.assertEqual([site.offset for site in sites.find(image)], [0x100, 0x500])

    def test_a_single_kind_can_be_asked_for(self):
        image = image_with({0x100: sites.STA_PORT, 0x200: sites.LDA_PORT})

        found = sites.find(image, [sites.KIND_WRITE])

        self.assertEqual([site.kind for site in found], [sites.KIND_WRITE])

    def test_a_site_carries_the_address_it_is_reached_through(self):
        image = image_with({0x20123: sites.STA_PORT})

        found = sites.find(image)[0]

        self.assertEqual((found.bank, found.address), (4, 0x8123))

    def test_the_status_poll_is_not_mistaken_for_a_port_read(self):
        image = image_with({0x100: sites.LDA_STATUS})

        self.assertEqual([site.kind for site in sites.find(image)], [sites.KIND_STATUS])


class TrampolineTest(unittest.TestCase):
    def test_a_call_to_each_trampoline_is_recognised(self):
        image = image_with(
            {0x20000 + 3 * n: sites.call_to(address) for n, address in enumerate(sites.TRAMPOLINES)}
        )

        found = sites.find_trampoline_calls(image)

        self.assertEqual([site.trampoline for site in found], list(sites.TRAMPOLINES))

    def test_a_call_outside_the_bank_that_reaches_the_chip_is_left_alone(self):
        image = image_with({0x08000: sites.call_to(0x0080)})

        self.assertEqual(sites.find_trampoline_calls(image), [])

    def test_a_call_to_an_ordinary_address_is_not_a_trampoline_call(self):
        image = image_with({0x20000: bytes([0x20, 0x00, 0x90])})

        self.assertEqual(sites.find_trampoline_calls(image), [])

    def test_the_measured_counts_are_held(self):
        image = image_with(
            {
                **{0x20000 + 3 * n: sites.call_to(0x0080) for n in range(2)},
                **{0x21000 + 3 * n: sites.call_to(0x0084) for n in range(5)},
                **{0x22000 + 3 * n: sites.call_to(0x0088) for n in range(4)},
                **{0x23000: sites.call_to(0x008C)},
            }
        )

        counted = sites.verify_trampoline_calls(sites.find_trampoline_calls(image))

        self.assertEqual(counted, {0x0080: 2, 0x0084: 5, 0x0088: 4, 0x008C: 1})

    def test_a_missing_call_is_refused(self):
        image = image_with({0x20000: sites.call_to(0x0080)})

        with self.assertRaises(sites.UnexpectedImage):
            sites.verify_trampoline_calls(sites.find_trampoline_calls(image))


class VerifyTest(unittest.TestCase):
    def test_an_image_with_the_measured_surface_is_accepted(self):
        image = image_with(
            {
                **{0x100 + 4 * n: sites.STA_PORT for n in range(51)},
                **{0x1000 + 4 * n: sites.LDA_PORT for n in range(4)},
                **{0x2000 + 4 * n: sites.LDA_STATUS for n in range(5)},
                **{0x3000 + 3 * n: sites.MVN_TO_PORT for n in range(16)},
                **{0x4000 + 3 * n: sites.MVN_FROM_PORT for n in range(2)},
            }
        )

        counted = sites.verify(sites.find(image))

        self.assertEqual(counted[sites.KIND_WRITE], 51)

    def test_an_image_with_too_few_sites_is_refused(self):
        image = image_with({0x100: sites.STA_PORT})

        with self.assertRaises(sites.UnexpectedImage) as raised:
            sites.verify(sites.find(image))

        self.assertIn("expected 51 found 1", str(raised.exception))

    def test_an_unmeasured_region_is_refused_rather_than_guessed(self):
        with self.assertRaises(sites.UnexpectedImage):
            sites.verify([], region="Mars")


class CensusTest(unittest.TestCase):
    def test_a_kind_with_no_sites_is_still_reported(self):
        self.assertEqual(sites.census([])[sites.KIND_DRAIN], 0)

    def test_banks_are_reported_without_repeats(self):
        image = image_with({0x100: sites.STA_PORT, 0x20100: sites.STA_PORT})

        self.assertEqual(sites.banks_touched(sites.find(image)), [0, 4])


@unittest.skipUnless(RETAIL.exists(), "the retail dump is supplied by the builder")
class RetailTest(unittest.TestCase):
    def setUp(self):
        self.image = RETAIL.read_bytes()

    def test_the_measured_surface_is_the_one_the_dump_carries(self):
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

    def test_every_site_lives_in_the_two_banks_that_drive_the_chip(self):
        self.assertEqual(sites.banks_touched(sites.find(self.image)), [0x00, 0x04])

    def test_the_status_polls_sit_where_they_were_measured(self):
        found = sites.find(self.image, [sites.KIND_STATUS])

        self.assertEqual(
            [(site.bank, site.address) for site in found],
            [(0x00, 0x9887), (0x04, 0x84E3), (0x04, 0x8898), (0x04, 0x9775), (0x04, 0x9886)],
        )

    def test_the_port_reads_sit_where_they_were_measured(self):
        found = sites.find(self.image, [sites.KIND_READ])

        self.assertEqual([site.address for site in found], [0x86D3, 0x86D8, 0x86DE, 0x86E2])

    def test_the_dump_carries_the_measured_trampoline_calls(self):
        counted = sites.verify_trampoline_calls(sites.find_trampoline_calls(self.image))

        self.assertEqual(counted, {0x0080: 2, 0x0084: 5, 0x0088: 4, 0x008C: 1})

    def test_every_trampoline_call_that_can_reach_the_chip_is_in_one_bank(self):
        found = sites.find_trampoline_calls(self.image)

        self.assertEqual({site.bank for site in found}, {0x04})


if __name__ == "__main__":
    unittest.main(verbosity=2)
