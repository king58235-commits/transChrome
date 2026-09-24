from config import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH_BYTES

BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH_BYTES


class AudioBuffer:
    """Accumulates raw PCM16 mono audio bytes received from the extension."""

    def __init__(self):
        self._data = bytearray()

    def append(self, chunk: bytes) -> None:
        self._data.extend(chunk)

    def duration_seconds(self) -> float:
        return len(self._data) / BYTES_PER_SECOND

    def size_bytes(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        self._data.clear()

    def take_and_clear(self) -> bytes:
        data = bytes(self._data)
        self._data.clear()
        return data

    def peek_bytes(self) -> bytes:
        return bytes(self._data)
