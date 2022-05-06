from io import SEEK_CUR, SEEK_SET, SEEK_END

_INITIAL_CAPACITY = 16
_GROWTH_FACTOR = 2.0


class UnsupportedError(Exception):
    """
    An error denoting the operation is not supported
    """


class Buffer:

    def __init__(self, initial_capacity: int = _INITIAL_CAPACITY, growth_factor: float = _GROWTH_FACTOR,
                 target: bytearray = None):
        # Initial buffer vars.
        self.growth_factor = growth_factor
        # Length & position vars.
        self.bit_position = 0
        self._bit_length = 0

        if target is not None:
            len_ = len(target)
            if len_ == 0:
                raise ValueError("The specified buffer target must have nonzero length")
            self._target = target
            self._resizable = False
            self._bit_length = len_ << 3
        else:
            self._target = bytearray(max(_INITIAL_CAPACITY, initial_capacity))
            self._resizable = True

    @property
    def growth_factor(self):
        return self._growth_factor

    @growth_factor.setter
    def growth_factor(self, value: float):
        self._growth_factor = max(1.0, value)

    @property
    def resizable(self):
        return self._resizable

    @property
    def length(self):
        return self._bit_length >> 3 + (1 if self._bit_length & 7 else 0)

    @length.setter
    def length(self, value: int):
        if value < 0:
            raise ValueError("Cannot set a negative length!")
        if value > self.capacity:
            self._grow(value - self.capacity)
        self._bit_length = value << 3
        self.bit_position = min(value << 3, self.bit_position)

    def __len__(self):
        return self.length

    @property
    def position(self):
        return self.bit_position >> 3

    @position.setter
    def position(self, value: int):
        self.bit_position = value << 3

    @property
    def bit_length(self):
        return self._bit_length

    @property
    def bit_aligned(self):
        return self.bit_position & 7 == 0

    @property
    def capacity(self):
        return len(self._target)

    def target(self):
        return self._target

    @capacity.setter
    def capacity(self, value: int):
        if value < self.length:
            raise ValueError("New capacity too small!")
        self._set_capacity(value)

    def _set_capacity(self, value: int):
        if not self._resizable:
            raise UnsupportedError("Can't resize non resizable buffer")
        new_array = bytearray(value)
        len_ = min(value, self.capacity)
        new_array[:len_] = self._target[:len_]
        if value < self.capacity:
            self.bit_position = value << 3
        self._target = new_array

    def _grow(self, delta: int):
        value = delta + self.capacity
        if self.capacity >= (1 << 30):
            new_capacity = max(value, (1 << 31) - 1)
        else:
            new_capacity = max(max(value, 256), self.capacity * 2)
        self._set_capacity(new_capacity)

    def _has_data_to_read(self):
        return self.position < self.length

    def _read_byte_misaligned(self):
        r = self.bit_position & 7
        l = self._target[self.position] >> r
        self.bit_position += 8
        u = self._target[self.bit_position >> 3] << (8 - r)
        return l | u

    def _read_byte_aligned(self):
        u = self._target[self.position]
        self.position += 1
        return u

    def _read_byte(self):
        return self._read_byte_aligned() if self.bit_aligned else self._read_byte_misaligned()

    def read_byte(self):
        return self._read_byte() if self._has_data_to_read() else -1

    def read_bit(self):
        b = self._target[self.position]
        self.bit_position += 1
        return b & (1 << (self.bit_position & 7)) != 0

    def read(self, into: bytearray, offset: int, count: int):
        len_ = min(count, self.capacity - self.position - 1 + int(self.bit_aligned))
        for idx in range(len_):
            into[offset + idx] = self._read_byte()
        return len_

    def seek(self, offset: int, origin: int):
        if origin == SEEK_SET:
            self.bit_position = max(0, offset) << 3
        elif origin == SEEK_CUR:
            if offset > 0:
                self.bit_position = max(self.bit_position + offset << 3, self.capacity << 3)
            elif offset < 0:
                self.bit_position = self.bit_position - (self.capacity - offset) << 3
        elif origin == SEEK_END:
            self.bit_position = max(0, self.capacity - offset) << 3
        else:
            raise ValueError(f"Invalid seek origin: {origin}")

    def write(self, from_: bytearray, offset: int, count: int):
        position = self.position
        if self.bit_aligned:
            if position + count >= self.capacity:
                self._grow(count)
            self._target[position:position + count] = from_[offset:offset + count]
        else:
            if position + count + 1 >= self.capacity:
                self._grow(count)
            for idx in range(count):
                self._write_misaligned(from_[offset + idx])

    def write_byte(self, value: int):
        if value < 0 or value > 255:
            raise ValueError("Value to write must be in range(0, 256)")
        if self.bit_aligned:
            if self.position + 1 >= self.capacity:
                self._grow(1)
            self._target[self.position] = value
            self.position += 1
        else:
            if self.position + 2 >= self.capacity:
                self._grow(1)
            self._write_misaligned(value)
        self._update_length()

    def _update_length(self):
        if self.bit_position > self._bit_length:
            self._bit_length = self.bit_position

    def _write_misaligned(self, value: int):
        r = self.bit_position & 7
        rc = 8 - r
        p = self.position
        self._target[p + 1] = (self._target[p + 1] & (255 << r)) | (value >> rc)
        self._target[p] = (self._target[p] & (255 >> rc)) | (value << r)
        self.bit_position += 8

    def write_bit(self, bit: bool):
        p = self.position
        if self.bit_aligned and self.position == self.capacity:
            self._grow(1)
        r = self.bit_position & 7
        self._target[p] = (self._target[p] & ~(1 << r)) | (int(bit) << r)
        self.bit_position += 1
        self._update_length()
