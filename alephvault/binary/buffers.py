from typing import Iterable, Union
from warnings import warn
from io import SEEK_CUR, SEEK_SET, SEEK_END

_INITIAL_CAPACITY = 16


class UnsupportedError(Exception):
    """
    An error denoting the operation is not supported
    """


class Buffer:
    """
    A buffer is a special kind of buffered stream which also accounts
    for misaligned reads and writes (e.g. bits being read and written).
    """

    def __init__(self, initial_capacity: int = _INITIAL_CAPACITY, target: bytearray = None):
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
    def resizable(self):
        """
        Whether the stream is resizable or not.
        """

        return self._resizable

    @property
    def length(self):
        """
        The current length, in bytes (rounded up).
        """

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
        """
        The current length, in bytes (rounded up).
        """

        return self.length

    @property
    def position(self):
        """
        The current position, in bytes (rounded down).
        """

        return self.bit_position >> 3

    @position.setter
    def position(self, value: int):
        """
        Sets the current position, in bytes.
        :param value: The position, in bytes, to set.
        """

        self.bit_position = value << 3

    @property
    def bit_length(self):
        """
        The current length of the contents, in bits.
        """

        return self._bit_length

    @property
    def bit_aligned(self):
        """
        Whether the current length of the contents is in multiples of 8.
        """

        return self.bit_position & 7 == 0

    @property
    def capacity(self):
        """
        Gets the underlying buffer capacity.
        """

        return len(self._target)

    @capacity.setter
    def capacity(self, value: int):
        """
        Sets the underlying buffer capacity.
        :param value: The new capacity.
        """

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

    @property
    def target(self):
        """
        The underlying buffer.
        """

        return self._target

    # Compatibility with the binary stream protocol:

    def seek(self, offset: int, whence: int = SEEK_SET):
        """
        Moves the pointer to the appropriate position in the buffer.
        This operation can be a bit dangerous for this stream type
        if used inappropriately.

        >> offset * 8 (clamped) is used for SEEK_SET.
        >> (capacity - offset) * 8 (clamped) is used for SEEK_END.
        >> (bit_position + offset * 8) (clamped) is used for SEEK_CUR.

        :param offset: The offset to seek.
        :param whence: The reference point.
        """

        def _clamp(v):
            return max(0, min(self.capacity << 3, v))

        if whence == SEEK_SET:
            self.bit_position = _clamp(offset << 3)
        elif whence == SEEK_CUR:
            self.bit_position = _clamp(self.bit_position + offset << 3)
        elif whence == SEEK_END:
            self.bit_position = _clamp((self.capacity - offset) << 3)
        else:
            raise ValueError(f"Invalid seek origin: {whence}")

    def tell(self):
        """
        The position to tell is byte-wise.
        :return:
        """

        warn("The tell() method may lack of precision for this bit-wise stream, "
             "in particular when the stream is misaligned")
        return self.position

    def close(self):
        """
        Nothing to do here.
        """

    def seekable(self):
        """
        This stream is seekable, despite it being dangerous.
        :return: True
        """

        return True

    def readable(self):
        """
        This stream is readable.
        :return: True
        """

        return True

    def writable(self):
        """
        This stream is writable.
        :return: True
        """

        return True

    def closed(self):
        """
        This stream is never closed.
        :return: False
        """

        return False

    def truncate(self, l: int = 0):
        """
        This stream cannot be truncated.
        :param l: The length to truncate to.
        :return:
        """

        raise UnsupportedError("This stream cannot be truncated")

    def readline(self, size: int = -1, /):
        """
        This stream is not line-wise. Pure binary.
        """

        raise UnsupportedError("This stream cannot read lines")

    def readlines(self, size: int = -1, /):
        """
        This stream is not line-wise. Pure binary.
        """

        raise UnsupportedError("This stream cannot read lines")

    def readinto(self, into: bytearray, /, offset: int = 0, size: int = -1):
        """
        Reads data into a given bytearray.
        :param into: The array to read into.
        :param offset: The offset to start, inside the array.
        :param size: The size to read. A negative value reads all.
        :return: The number of bytes read.
        """

        max_length = self.capacity - self.position - 1 + int(self.bit_aligned)
        if size < 0:
            size = len(into)
        len_ = min(size, max_length)
        for idx in range(len_):
            into[offset + idx] = self._read_byte()
        return len_

    readinto1 = readinto

    def read(self, size: int = -1):
        """
        Reads data into a new byte array, up to certain length.
        :param size: The size to read. A negative value reads all.
        :return: The bytes read (the array).
        """

        arr = bytearray(self.length)
        len_ = self.readinto(arr, offset=0, size=size)
        return arr[:len_]

    read1 = read

    def writelines(self, lines: Iterable[str]):
        """
        This stream is not line-wise. Pure binary.
        :param lines: The lines to write.
        """

        raise UnsupportedError("This stream cannot write lines")

    def write(self, b: Union[bytearray, bytes], offset: int = 0, size: int = -1):
        """
        Writes bytes from a given source.
        :param b: The bytes source.
        :param offset: The offset to write.
        :param size: The size to write. A negative value reads all.
        """

        position = self.position
        len_ = len(b)
        if size < 0:
            size = len_
        elif size > len_:
            size = len_

        if self.bit_aligned:
            if position + size >= self.capacity:
                self._grow(size)
            self._target[position:position + size] = b[offset:offset + size]
        else:
            if position + size + 1 >= self.capacity:
                self._grow(size)
            for idx in range(size):
                self._write_misaligned(b[offset + idx])

        return size

    def getbuffer(self):
        """
        Gets the underlying buffer.
        """

        return self.target

    def getvalue(self):
        """
        Gets the contents of the underlying buffer.
        :return: The contents
        """

        return bytes(self.target)

    # Extra read & write methods:

    def read_byte(self):
        """
        Reads a single byte. On EOF, returns -1.
        :return: A byte, or -1 on EOF.
        """

        return self._read_byte() if self._has_data_to_read() else -1

    def read_bit(self):
        """
        Reads a single bit. On EOF, returns None
        :return: The bit (as bool) or None.
        """

        if self.bit_position >= self.bit_length:
            return None
        b = self._target[self.position]
        self.bit_position += 1
        return b & (1 << (self.bit_position & 7)) != 0

    def write_byte(self, value: int):
        """
        Writes a single byte.
        :param value: The byte to write.
        """

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

    def write_bit(self, bit: bool):
        """
        Writes a single bit.
        :param bit: The bit to write.
        """

        p = self.position
        if self.bit_aligned and self.position == self.capacity:
            self._grow(1)
        r = self.bit_position & 7
        self._target[p] = (self._target[p] & ~(1 << r)) | (int(bit) << r)
        self.bit_position += 1
        self._update_length()

    # Private methods:

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
