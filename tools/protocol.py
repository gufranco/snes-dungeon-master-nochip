from typing import Any, override

"""How many bytes each DSP-2 command takes and gives, tracked from the stream.

The part answers what it answers, and nothing here has an opinion about that.
What a driver still has to know is the shape of an exchange: how many bytes a
command wants before it acts, and how many come back afterwards. A console knows
that because the routine driving the chip was written knowing it, and this is the
same knowledge in the same place.

It is worth being exact about the division, because the whole project rests on
it. The part decides every value. This decides only how many values there are.
Nothing here computes a merge, a scale or a product; ask the part.

That division is why this exists at all. The model that used to sit here could be
asked how many bytes it still owed, because it had computed them. Silicon cannot
be asked: the status register says the part wants attention and nothing more. So
the count moves to the side that always had it.
"""

TILE = 0x01
TRANSPARENT = 0x03
MERGE = 0x05
MIRROR = 0x06
MULTIPLY = 0x09
SCALE = 0x0D
SYNC = 0x0F

COMMANDS = (TILE, TRANSPARENT, MERGE, MIRROR, MULTIPLY, SCALE, SYNC)

TILE_BYTES = 32

MULTIPLY_BYTES = 4

HEADER_INPUT = {
    TILE: TILE_BYTES,
    TRANSPARENT: 1,
    MERGE: 1,
    MIRROR: 1,
    MULTIPLY: MULTIPLY_BYTES,
    SCALE: 2,
}


class Shape:
    def __init__(self) -> None:
        self.command = None
        self.waiting_for_command = True
        self.wanted = 0
        self.taken = 0
        self.owed = 0
        self.transparent = None
        self._armed: dict[Any, Any] = {}
        self._held: dict[Any, Any] = {}
        self._lengths: list[int] = []
        self._reading_lengths = False

    @property
    def produced(self) -> Any:
        return self.owed

    @property
    def expecting_input(self) -> bool:
        return not self.waiting_for_command

    @property
    def at_boundary(self) -> bool:
        return self.waiting_for_command and self.owed == 0

    def was_read(self) -> None:
        if self.owed:
            self.owed -= 1

    def wrote(self, value: Any) -> None:
        value &= 0xFF

        if self.waiting_for_command:
            self.command = value
            self.taken = 0
            self.waiting_for_command = False
            self.wanted = HEADER_INPUT.get(value, 0)
            self._lengths = []
            self._reading_lengths = True
        else:
            if self._reading_lengths and self.taken < len(self._headers()):
                self._lengths.append(value)
            self.taken += 1

        if self.wanted == self.taken:
            self.waiting_for_command = True
            self._acted(value)

    def _headers(self) -> Any:
        if self.command in (MERGE, MIRROR):
            return (0,)
        if self.command == SCALE:
            return (0, 1)
        return ()

    def _arm(self, wanted: Any, value: Any) -> None:
        self.taken = 0
        self.wanted = wanted
        self._reading_lengths = False
        if value:
            self.waiting_for_command = False

    def _acted(self, value: Any) -> None:
        command = self.command

        if command == TILE:
            self.owed = TILE_BYTES
        elif command == MULTIPLY:
            self.owed = MULTIPLY_BYTES
        elif command == TRANSPARENT:
            self.transparent = value
        elif command == MERGE:
            self._sized(command, lambda length: 2 * length, value)
        elif command == MIRROR:
            self._sized(command, lambda length: length, value)
        elif command == SCALE:
            self._scaled(value)

    @property
    def _first(self) -> Any:
        return self._lengths[0] if self._lengths else 0

    def _sized(self, command: Any, payload_for: Any, value: Any) -> None:
        if self._armed.pop(command, None) is not None:
            self.owed = self._held[command]
            return
        length = self._first
        self._held[command] = length
        self._armed[command] = True
        self._arm(payload_for(length), value)

    def _scaled(self, value: Any) -> None:
        if self._armed.pop(SCALE, None) is not None:
            self.owed = self._held["scale_out"]
            return
        taking = self._lengths[0] if self._lengths else 0
        giving = self._lengths[1] if len(self._lengths) > 1 else 0
        self._held["scale_out"] = giving
        self._armed[SCALE] = True
        self._arm((taking + 1) >> 1, value)

    @override
    def __repr__(self) -> str:
        where = "between commands" if self.waiting_for_command else f"inside {self.command:#04x}"
        return f"<Shape {where}, {self.owed} owed>"
