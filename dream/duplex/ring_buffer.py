"""Circular audio jitter and ring buffer for streaming duplex PCM frames."""

from __future__ import annotations

import asyncio
from typing import Any


class AudioRingBuffer:
    """Async-safe circular byte ring buffer for real-time PCM audio streams."""

    def __init__(
        self,
        capacity_bytes: int = 16000 * 2 * 10,
    ) -> None:  # Default 10 seconds of 16kHz 16-bit
        self.capacity = capacity_bytes
        self._buffer = bytearray(capacity_bytes)
        self._write_pos: int = 0
        self._read_pos: int = 0
        self._size: int = 0
        self._lock = asyncio.Lock()
        self._underruns: int = 0
        self._overruns: int = 0

    @property
    def available_read(self) -> int:
        """Number of bytes currently available for reading."""
        return self._size

    @property
    def available_write(self) -> int:
        """Number of free bytes available for writing."""
        return self.capacity - self._size

    @property
    def underruns(self) -> int:
        """Total underrun occurrences."""
        return self._underruns

    @property
    def overruns(self) -> int:
        """Total overrun occurrences."""
        return self._overruns

    async def write(self, data: bytes) -> int:
        """Write bytes into the circular buffer. Overwrites oldest data if full."""
        if not data:
            return 0

        async with self._lock:
            data_len = len(data)
            if data_len > self.capacity:
                # Truncate to capacity keeping most recent
                data = data[-self.capacity :]
                data_len = self.capacity

            # Check if write causes overrun
            if data_len > (self.capacity - self._size):
                self._overruns += 1
                excess = data_len - (self.capacity - self._size)
                self._read_pos = (self._read_pos + excess) % self.capacity
                self._size -= excess

            # Write in 1 or 2 chunks
            first_chunk = min(data_len, self.capacity - self._write_pos)
            self._buffer[self._write_pos : self._write_pos + first_chunk] = data[:first_chunk]

            second_chunk = data_len - first_chunk
            if second_chunk > 0:
                self._buffer[0:second_chunk] = data[first_chunk:]

            self._write_pos = (self._write_pos + data_len) % self.capacity
            self._size += data_len
            return data_len

    async def read(self, num_bytes: int) -> bytes:
        """Read requested number of bytes from buffer. Returns partial or empty if not enough."""
        if num_bytes <= 0:
            return b""

        async with self._lock:
            if self._size == 0:
                self._underruns += 1
                return b""

            to_read = min(num_bytes, self._size)
            first_chunk = min(to_read, self.capacity - self._read_pos)
            out = bytes(self._buffer[self._read_pos : self._read_pos + first_chunk])

            second_chunk = to_read - first_chunk
            if second_chunk > 0:
                out += bytes(self._buffer[0:second_chunk])

            self._read_pos = (self._read_pos + to_read) % self.capacity
            self._size -= to_read
            return out

    async def flush(self) -> bytes:
        """Read and clear all remaining bytes in the buffer."""
        async with self._lock:
            if self._size == 0:
                return b""

            to_read = self._size
            first_chunk = min(to_read, self.capacity - self._read_pos)
            out = bytes(self._buffer[self._read_pos : self._read_pos + first_chunk])

            second_chunk = to_read - first_chunk
            if second_chunk > 0:
                out += bytes(self._buffer[0:second_chunk])

            self._read_pos = 0
            self._write_pos = 0
            self._size = 0
            return out

    async def clear(self) -> None:
        """Immediately drop all buffer contents."""
        async with self._lock:
            self._read_pos = 0
            self._write_pos = 0
            self._size = 0

    def get_stats(self) -> dict[str, Any]:
        """Return diagnostic stats of the ring buffer."""
        return {
            "capacity_bytes": self.capacity,
            "used_bytes": self._size,
            "utilization_pct": round((self._size / self.capacity) * 100, 2),
            "underruns": self._underruns,
            "overruns": self._overruns,
        }
