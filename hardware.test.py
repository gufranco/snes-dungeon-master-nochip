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


class ModelTest(unittest.TestCase):
    def setUp(self):
        hardware.install()

    def test_the_processor_is_the_one_that_was_vendored(self):
        cpu = importlib.import_module("mos65xx")

        self.assertTrue(hasattr(cpu, "Cpu"))
        self.assertIn("65816", cpu.MODELS)

    def test_the_coprocessor_is_the_one_that_was_vendored(self):
        chip = importlib.import_module("dsp2")

        self.assertTrue(hasattr(chip, "Chip"))
        self.assertEqual(chip.COMMAND_MERGE, 0x05)

    def test_the_cartridge_map_is_the_one_that_was_vendored(self):
        found = importlib.import_module("mapper")

        self.assertTrue(hasattr(found, "resolve"))
        self.assertEqual(found.ENABLE, 0x420B)

    def test_every_model_reports_a_released_version(self):
        for module in ("mos65xx", "dsp2", "mapper"):
            found = importlib.import_module(module)

            self.assertRegex(found.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
