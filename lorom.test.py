import unittest
from typing import Any, override

import lorom
import script

ROM_BYTES = 0x80000


class MemoryTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.memory = lorom.LoRomMemory(bytes(range(256)) * 1024)

    def test_work_ram_reads_back_what_was_written(self) -> None:
        self.memory.write8(0x7E1234, 0xA5)

        self.assertEqual(self.memory.read8(0x7E1234), 0xA5)

    def test_low_work_ram_is_mirrored_into_the_low_banks(self) -> None:
        self.memory.write8(0x7E0123, 0x5A)

        self.assertEqual(self.memory.read8(0x000123), 0x5A)

    def test_the_cartridge_is_read_only(self) -> None:
        before = self.memory.read8(0x008000)

        self.memory.write8(0x008000, before ^ 0xFF)

        self.assertEqual(self.memory.read8(0x008000), before)

    def test_a_lorom_address_maps_to_its_linear_offset(self) -> None:
        rom = bytearray(0x80000)
        rom[0x8000] = 0x42
        memory = lorom.LoRomMemory(bytes(rom))

        self.assertEqual(memory.read8(0x018000), 0x42)


class MemoryMapTest(unittest.TestCase):
    def _memory(self) -> Any:
        return lorom.LoRomMemory(bytes(ROM_BYTES))

    def test_the_second_work_ram_bank_is_the_upper_half(self) -> None:
        memory = self._memory()
        memory.write8(0x7F0001, 0xAB)

        self.assertEqual(memory.wram[0x10001], 0xAB)

    def test_the_first_work_ram_bank_is_the_lower_half(self) -> None:
        memory = self._memory()
        memory.write8(0x7E0001, 0xCD)

        self.assertEqual(memory.wram[0x0001], 0xCD)

    def test_the_mirror_in_a_low_bank_reaches_the_same_bytes(self) -> None:
        memory = self._memory()
        memory.write8(0x000001, 0xEF)

        self.assertEqual(memory.wram[0x0001], 0xEF)

    def test_an_address_in_neither_reads_from_the_cartridge(self) -> None:
        memory = self._memory()

        self.assertEqual(memory.read8(0x018000), 0x00)

    def test_and_a_work_ram_bank_is_never_read_as_cartridge(self) -> None:
        self.assertIsNone(self._memory()._rom_offset(0x7E0000))


script.entry(__name__, unittest.main)
