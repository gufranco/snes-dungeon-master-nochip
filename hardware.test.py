import importlib
import sys
import unittest

import hardware


class PathTest(unittest.TestCase):
    def test_every_model_it_names_is_on_disk(self):
        missing = [name for name in hardware.PACKAGES if not hardware.root_of(name).is_dir()]

        self.assertEqual(missing, [])

    def test_a_model_it_does_not_carry_is_refused_by_name(self):
        with self.assertRaises(hardware.UnknownPackage):
            hardware.root_of("nonsense")

    def test_the_refusal_lists_what_is_available(self):
        with self.assertRaises(hardware.UnknownPackage) as raised:
            hardware.root_of("nonsense")

        self.assertIn("mos65xx", str(raised.exception))

    def test_installing_puts_every_model_on_the_import_path(self):
        hardware.install()

        for name in hardware.PACKAGES:
            self.assertIn(str(hardware.root_of(name)), sys.path)

    def test_installing_twice_does_not_stack_the_path(self):
        hardware.install()
        before = list(sys.path)

        hardware.install()

        self.assertEqual(sys.path, before)


class LoadTest(unittest.TestCase):
    def test_a_model_comes_back_by_the_name_it_is_published_under(self):
        found = hardware.load("mapper")

        self.assertTrue(hasattr(found, "resolve"))

    def test_loading_a_model_it_does_not_carry_is_refused_before_importing(self):
        with self.assertRaises(hardware.UnknownPackage):
            hardware.load("nonsense")

    def test_loading_the_same_model_twice_gives_the_same_module(self):
        self.assertIs(hardware.load("mapper"), hardware.load("mapper"))


class ModelTest(unittest.TestCase):
    def setUp(self):
        hardware.install()

    def test_the_processor_is_the_one_that_was_vendored(self):
        cpu = importlib.import_module("mos65xx")

        self.assertTrue(hasattr(cpu, "Cpu"))
        self.assertIn("65816", cpu.MODELS)

    def test_the_coprocessor_is_the_one_that_was_vendored(self):
        chip = importlib.import_module("snesdsp")

        self.assertTrue(hasattr(chip, "Dsp"))
        self.assertIn("dsp2", chip.MODELS)

    def test_and_it_runs_the_part_rather_than_describing_it(self):
        chip = importlib.import_module("snesdsp")

        self.assertTrue(hasattr(chip, "why_not"))
        self.assertTrue(hasattr(chip, "NoFirmware"))

    def test_the_cartridge_map_is_the_one_that_was_vendored(self):
        found = importlib.import_module("mapper")

        self.assertTrue(hasattr(found, "resolve"))
        self.assertEqual(found.ENABLE, 0x420B)

    def test_the_image_handling_is_the_one_that_was_vendored(self):
        found = importlib.import_module("romimage")

        self.assertTrue(hasattr(found.dump, "read"))
        self.assertTrue(hasattr(found.rewrite, "declare_rom_only"))

    def test_the_image_package_reads_the_map_this_project_pinned(self):
        found = importlib.import_module("romimage")
        used = importlib.import_module("mapper")

        self.assertIs(found.rewrite.mapper, used)

    def test_every_model_reports_a_released_version(self):
        for module in hardware.PACKAGES:
            found = importlib.import_module(module)

            self.assertRegex(found.__version__, r"^\d+\.\d+\.\d+$")


class FirmwareTest(unittest.TestCase):
    """That the part is told where this project keeps the microcode it runs.

    The coprocessor model looks in what its variable names and then beside
    itself, and neither of those reaches a project two levels up. Without this
    the part would report that it has no image on a machine that has one.
    """

    def test_this_project_s_directory_is_named(self):
        where = {}

        hardware.name_firmware(where)

        self.assertIn(str(hardware.FIRMWARE), where[hardware.FIRMWARE_VARIABLE])

    def test_a_directory_somebody_already_named_is_kept(self):
        where = {hardware.FIRMWARE_VARIABLE: "/somewhere/else"}

        found = hardware.name_firmware(where)

        self.assertIn("/somewhere/else", found)

    def test_and_this_project_comes_first(self):
        where = {hardware.FIRMWARE_VARIABLE: "/somewhere/else"}

        found = hardware.name_firmware(where)

        self.assertTrue(found.startswith(str(hardware.FIRMWARE)))

    def test_naming_it_twice_does_not_name_it_twice(self):
        where = {}

        hardware.name_firmware(where)
        found = hardware.name_firmware(where)

        self.assertEqual(found.count(str(hardware.FIRMWARE)), 1)

    def test_installing_names_it_too(self):
        where = {}

        hardware.install(where)

        self.assertIn(hardware.FIRMWARE_VARIABLE, where)


if __name__ == "__main__":
    unittest.main()
