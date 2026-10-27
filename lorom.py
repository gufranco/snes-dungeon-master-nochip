from typing import Any


class LoRomMemory:
    def __init__(self, rom: Any) -> None:
        self.rom = rom
        self.wram = bytearray(0x20000)

    def _wram_offset(self, address: int) -> int | None:
        bank = (address >> 16) & 0xFF
        offset = address & 0xFFFF
        if bank == 0x7E:
            return offset
        if bank == 0x7F:
            return 0x10000 + offset
        if (bank < 0x40 or 0x80 <= bank < 0xC0) and offset < 0x2000:
            return offset
        return None

    def _rom_offset(self, address: int) -> int | None:
        bank = (address >> 16) & 0xFF
        offset = address & 0xFFFF
        if bank in (0x7E, 0x7F) or offset < 0x8000:
            return None
        linear = (bank & 0x7F) * 0x8000 + (offset - 0x8000)
        return linear % len(self.rom)

    def read8(self, address: int) -> int:
        at = self._wram_offset(address)
        if at is not None:
            return self.wram[at]
        at = self._rom_offset(address)
        return self.rom[at] if at is not None else 0x00

    def write8(self, address: Any, value: Any) -> None:
        at = self._wram_offset(address)
        if at is not None:
            self.wram[at] = value & 0xFF
