# coding=utf-8
"""
Jin10 binary protocol helpers.
"""

from __future__ import annotations

import struct


class BinaryReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read_u16(self) -> int:
        value = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return value

    def read_i16(self) -> int:
        value = struct.unpack_from("<h", self.data, self.pos)[0]
        self.pos += 2
        return value

    def read_u32(self) -> int:
        value = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return value

    def read_i32(self) -> int:
        value = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return value

    def read_string(self) -> str:
        length = self.read_u16()
        if self.pos + length > len(self.data):
            raise ValueError(f"string length out of range: {length}")
        value = self.data[self.pos:self.pos + length].decode("utf-8")
        self.pos += length
        return value

    def remaining(self) -> int:
        return len(self.data) - self.pos


class BinaryWriter:
    def __init__(self):
        self.buffer = bytearray()

    def write_i16(self, value: int) -> None:
        self.buffer.extend(struct.pack("<h", value))

    def write_u16(self, value: int) -> None:
        self.buffer.extend(struct.pack("<H", value))

    def write_u32(self, value: int) -> None:
        self.buffer.extend(struct.pack("<I", value))

    def write_string(self, value: str) -> None:
        raw = value.encode("utf-8")
        self.write_u16(len(raw))
        self.buffer.extend(raw)

    def to_bytes(self) -> bytes:
        return bytes(self.buffer)


def xor_decrypt(data: bytes, key: str) -> bytes:
    if not data or not key:
        return data

    offset = ord(key[0])
    result = bytearray(len(data))
    for idx, value in enumerate(data):
        result[idx] = value ^ ord(key[(idx + offset) % len(key)])
    return bytes(result)


def xor_encrypt(data: bytes, key: str) -> bytes:
    return xor_decrypt(data, key)
