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
"""How many bytes each command wants before it first acts, lengths included.

A merge, a mirror and a scale ask for their lengths first and their data after,
so they appear here with only the length bytes and take the rest once they know
how much to take.
"""


class Shape:
    """Where a stream of bytes has got to, and what the part owes because of it."""

    def __init__(self):
        self.command = None
        self.waiting_for_command = True
        self.wanted = 0
        self.taken = 0
        self.owed = 0
        self.transparent = None
        self._armed = {}
        self._held = {}
        self._lengths = []
        self._reading_lengths = False

    @property
    def produced(self):
        """How many bytes of a finished result have not been read yet."""
        return self.owed

    @property
    def expecting_input(self):
        """Whether the part is still owed bytes before it can act."""
        return not self.waiting_for_command

    @property
    def at_boundary(self):
        """Whether a fresh part could take over here without losing anything.

        True when the stream is between commands and no result is waiting. A
        driver that breaks anywhere else splits a command from its payload, or
        its payload from its answer, and the part it hands over to knows neither.
        """
        return self.waiting_for_command and self.owed == 0

    def was_read(self):
        """One byte of the result taken by whoever is driving."""
        if self.owed:
            self.owed -= 1

    def wrote(self, value):
        """One byte given to the part, and what that leaves it owing."""
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

    def _headers(self):
        """The length bytes this command declares before its data."""
        if self.command in (MERGE, MIRROR):
            return (0,)
        if self.command == SCALE:
            return (0, 1)
        return ()

    def _arm(self, wanted, value):
        """Take the lengths, then decide whether data follows them.

        A non zero length means data comes next. A zero length leaves the part
        waiting for a command with the length still held, so the next appearance
        of that command runs immediately on the length it was already given.
        """
        self.taken = 0
        self.wanted = wanted
        self._reading_lengths = False
        if value:
            self.waiting_for_command = False

    def _acted(self, value):
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
    def _first(self):
        return self._lengths[0] if self._lengths else 0

    def _sized(self, command, payload_for, value):
        """A merge or a mirror: its length once, then that much data."""
        if self._armed.pop(command, None) is not None:
            self.owed = self._held[command]
            return
        length = self._first
        self._held[command] = length
        self._armed[command] = True
        self._arm(payload_for(length), value)

    def _scaled(self, value):
        """A scale: two lengths, then half the first rounded up in data."""
        if self._armed.pop(SCALE, None) is not None:
            self.owed = self._held["scale_out"]
            return
        taking = self._lengths[0] if self._lengths else 0
        giving = self._lengths[1] if len(self._lengths) > 1 else 0
        self._held["scale_out"] = giving
        self._armed[SCALE] = True
        self._arm((taking + 1) >> 1, value)

    def __repr__(self):
        where = "between commands" if self.waiting_for_command else f"inside {self.command:#04x}"
        return f"<Shape {where}, {self.owed} owed>"
