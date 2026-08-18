TILE_BYTES = 32
MULTIPLY_BYTES = 4
IDLE_BYTE = 0xFF

COMMAND_TILE = 0x01
COMMAND_TRANSPARENT = 0x03
COMMAND_MERGE = 0x05
COMMAND_MIRROR = 0x06
COMMAND_MULTIPLY = 0x09
COMMAND_SCALE = 0x0D
COMMAND_SYNC = 0x0F

UNIT = 0x10000

_LOW_PLANE_SHIFTS = (
    ((0x10, 3), (0x01, 6), (0x10, 1), (0x01, 4), (0x10, -1), (0x01, 2), (0x10, -3), (0x01, 0)),
    ((0x20, 2), (0x02, 5), (0x20, 0), (0x02, 3), (0x20, -2), (0x02, 1), (0x20, -4), (0x02, -1)),
)

_HIGH_PLANE_SHIFTS = (
    ((0x40, 1), (0x04, 4), (0x40, -1), (0x04, 2), (0x40, -3), (0x04, 0), (0x40, -5), (0x04, -2)),
    ((0x80, 0), (0x08, 3), (0x80, -2), (0x08, 1), (0x80, -4), (0x08, -1), (0x80, -6), (0x08, -3)),
)


def _shift(value, places):
    return (value << places) if places >= 0 else (value >> -places)


def tile(payload):
    if len(payload) != TILE_BYTES:
        raise ValueError(f"a tile conversion takes {TILE_BYTES} bytes, got {len(payload)}")

    low = bytearray()
    high = bytearray()
    for group in range(8):
        quad = payload[group * 4 : group * 4 + 4]
        ordered = (quad[0], quad[0], quad[1], quad[1], quad[2], quad[2], quad[3], quad[3])
        for pattern in _LOW_PLANE_SHIFTS:
            low.append(_pack_ordered(ordered, pattern))
        for pattern in _HIGH_PLANE_SHIFTS:
            high.append(_pack_ordered(ordered, pattern))
    return bytes(low + high)


def _pack_ordered(ordered, pattern):
    out = 0
    for value, (mask, places) in zip(ordered, pattern, strict=True):
        out |= _shift(value & mask, places)
    return out & 0xFF


class State:
    def __init__(self):
        self.transparent = 0x00

    def set_transparent(self, value):
        self.transparent = value & 0x0F


def merge(state, payload, length):
    if len(payload) != 2 * length:
        raise ValueError(f"a merge of {length} takes {2 * length} bytes, got {len(payload)}")

    colour = state.transparent
    under = payload[:length]
    over = payload[length:]
    out = bytearray(length)
    for index in range(length):
        c1 = under[index]
        c2 = over[index]
        high = c1 & 0xF0 if (c2 >> 4) == colour else c2 & 0xF0
        low = c1 & 0x0F if (c2 & 0x0F) == colour else c2 & 0x0F
        out[index] = high | low
    return bytes(out)


def mirror(payload, length):
    if len(payload) < length:
        raise ValueError(f"a mirror of {length} takes {length} bytes, got {len(payload)}")

    out = bytearray(length)
    for index in range(length):
        value = payload[index]
        out[length - 1 - index] = ((value << 4) | (value >> 4)) & 0xFF
    return bytes(out)


def multiply(payload):
    if len(payload) != MULTIPLY_BYTES:
        raise ValueError(f"a multiply takes {MULTIPLY_BYTES} bytes, got {len(payload)}")

    first = payload[0] | (payload[1] << 8)
    second = payload[2] | (payload[3] << 8)
    return (first * second).to_bytes(4, "little")


def _ratio(in_length, out_length):
    return (in_length << 17) // ((out_length << 1) + 1)


def scale(payload, in_length, out_length):
    wanted = (in_length + 1) >> 1
    if len(payload) < wanted:
        raise ValueError(f"a scale from {in_length} takes {wanted} bytes, got {len(payload)}")

    multiplier = UNIT if in_length <= out_length else _ratio(in_length, out_length)

    nibbles = []
    position = 0
    for _ in range(out_length * 2):
        index = position >> 16
        byte = payload[index >> 1] if (index >> 1) < len(payload) else 0
        nibbles.append(byte & 0x0F if index & 1 else (byte & 0xF0) >> 4)
        position += multiplier

    out = bytearray(out_length)
    for index in range(out_length):
        out[index] = (nibbles[index * 2] << 4) | nibbles[index * 2 + 1]
    return bytes(out)


_FIXED_INPUT = {
    COMMAND_TILE: TILE_BYTES,
    COMMAND_TRANSPARENT: 1,
    COMMAND_MULTIPLY: MULTIPLY_BYTES,
}

_LENGTH_COUNT = {
    COMMAND_MERGE: 1,
    COMMAND_MIRROR: 1,
    COMMAND_SCALE: 2,
}


class Chip:
    def __init__(self):
        self.state = State()
        self._reset()

    def _reset(self):
        self.command = None
        self.lengths = []
        self.parameters = bytearray()
        self.output = b""
        self.output_index = 0
        self._wanted_lengths = 0
        self._wanted_parameters = 0

    @property
    def pending_output(self):
        return len(self.output) - self.output_index

    def write(self, value):
        value &= 0xFF

        if self.command is None:
            self.command = value
            self.lengths = []
            self.parameters = bytearray()
            self.output = b""
            self.output_index = 0
            self._wanted_lengths = _LENGTH_COUNT.get(value, 0)
            self._wanted_parameters = _FIXED_INPUT.get(value, 0)
            if self._wanted_lengths == 0 and self._wanted_parameters == 0:
                self.command = None
            return

        if self._wanted_lengths > 0:
            self.lengths.append(value)
            self._wanted_lengths -= 1
            if self._wanted_lengths == 0:
                self._wanted_parameters = self._payload_size()
                if self._wanted_parameters == 0:
                    self._run()
            return

        self.parameters.append(value)
        self._wanted_parameters -= 1
        if self._wanted_parameters == 0:
            self._run()

    def _payload_size(self):
        if self.command == COMMAND_MERGE:
            return 2 * self.lengths[0]
        if self.command == COMMAND_MIRROR:
            return self.lengths[0]
        if self.command == COMMAND_SCALE:
            return (self.lengths[0] + 1) >> 1
        return 0

    def _run(self):
        payload = bytes(self.parameters)
        command = self.command
        self.command = None

        if command == COMMAND_TILE:
            self.output = tile(payload)
        elif command == COMMAND_TRANSPARENT:
            self.state.set_transparent(payload[0])
            self.output = b""
        elif command == COMMAND_MERGE:
            self.output = merge(self.state, payload, self.lengths[0])
        elif command == COMMAND_MIRROR:
            self.output = mirror(payload, self.lengths[0])
        elif command == COMMAND_MULTIPLY:
            self.output = multiply(payload)
        elif command == COMMAND_SCALE:
            self.output = scale(payload, self.lengths[0], self.lengths[1])
        else:
            self.output = b""
        self.output_index = 0

    def read(self):
        if self.output_index >= len(self.output):
            return IDLE_BYTE
        value = self.output[self.output_index]
        self.output_index += 1
        return value
