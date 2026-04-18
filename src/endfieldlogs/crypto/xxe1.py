from __future__ import annotations

import struct


def _rotl32(value: int, shift: int) -> int:
    value &= 0xFFFFFFFF
    return ((value << shift) & 0xFFFFFFFF) | (value >> (32 - shift))


def _quarter_round(state: list[int], a: int, b: int, c: int, d: int) -> None:
    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] = _rotl32(state[d] ^ state[a], 16)
    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] = _rotl32(state[b] ^ state[c], 12)
    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] = _rotl32(state[d] ^ state[a], 8)
    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] = _rotl32(state[b] ^ state[c], 7)


class XXE1:
    allowed_key_length = 32
    allowed_nonce_length = 12
    process_bytes_at_time = 64
    _SIGMA = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)

    def __init__(self, key: bytes, nonce: bytes, counter: int = 0) -> None:
        if len(key) != self.allowed_key_length:
            raise ValueError(f"XXE1 key length must be {self.allowed_key_length}")
        if len(nonce) != self.allowed_nonce_length:
            raise ValueError(f"XXE1 nonce length must be {self.allowed_nonce_length}")

        self._state = [0] * 16
        self._state[0:4] = list(self._SIGMA)
        self._state[4:12] = list(struct.unpack("<8I", key))
        self._state[12] = counter & 0xFFFFFFFF
        self._state[13:16] = list(struct.unpack("<3I", nonce))
        self._keystream = b""
        self._keystream_offset = self.process_bytes_at_time

    def _recalc_xor_stream(self) -> None:
        working = self._state.copy()
        for _ in range(10):
            _quarter_round(working, 0, 4, 8, 12)
            _quarter_round(working, 1, 5, 9, 13)
            _quarter_round(working, 2, 6, 10, 14)
            _quarter_round(working, 3, 7, 11, 15)
            _quarter_round(working, 0, 5, 10, 15)
            _quarter_round(working, 1, 6, 11, 12)
            _quarter_round(working, 2, 7, 8, 13)
            _quarter_round(working, 3, 4, 9, 14)

        block = [(working[i] + self._state[i]) & 0xFFFFFFFF for i in range(16)]
        self._keystream = struct.pack("<16I", *block)
        self._keystream_offset = 0
        self._state[12] = (self._state[12] + 1) & 0xFFFFFFFF
        if self._state[12] == 0:
            self._state[13] = (self._state[13] + 1) & 0xFFFFFFFF

    def process(self, data: bytes) -> bytes:
        if not data:
            return b""

        output = bytearray(len(data))
        src = memoryview(data)
        offset = 0
        while offset < len(src):
            if self._keystream_offset >= self.process_bytes_at_time:
                self._recalc_xor_stream()
            chunk = min(len(src) - offset, self.process_bytes_at_time - self._keystream_offset)
            key_stream = self._keystream[self._keystream_offset : self._keystream_offset + chunk]
            for idx in range(chunk):
                output[offset + idx] = src[offset + idx] ^ key_stream[idx]
            offset += chunk
            self._keystream_offset += chunk
        return bytes(output)
