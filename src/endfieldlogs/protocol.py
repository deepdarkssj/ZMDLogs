from __future__ import annotations

import zlib
from pathlib import Path
from typing import Any, Iterator

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

try:
    from .embedded_keys import CLIENT_NET_RSA_PRIVATE_KEY_B64
except ImportError:
    CLIENT_NET_RSA_PRIVATE_KEY_B64 = None


def decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    index = offset
    while index < len(data):
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return value, index
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")
    raise ValueError("incomplete varint")


def iter_fields(data: bytes) -> Iterator[tuple[int, int, bytes | int]]:
    index = 0
    while index < len(data):
        tag, index = decode_varint(data, index)
        field_no = tag >> 3
        wire = tag & 0x7
        if wire == 0:
            value, index = decode_varint(data, index)
            yield field_no, wire, value
        elif wire == 2:
            size, index = decode_varint(data, index)
            end = index + size
            if end > len(data):
                raise ValueError("field length overflow")
            yield field_no, wire, data[index:end]
            index = end
        elif wire == 5:
            end = index + 4
            if end > len(data):
                raise ValueError("fixed32 overflow")
            yield field_no, wire, data[index:end]
            index = end
        elif wire == 1:
            end = index + 8
            if end > len(data):
                raise ValueError("fixed64 overflow")
            yield field_no, wire, data[index:end]
            index = end
        else:
            raise ValueError(f"unsupported wire type: {wire}")


def parse_head(data: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        for field_no, wire, value in iter_fields(data):
            if wire != 0 or not isinstance(value, int):
                continue
            if field_no == 1:
                out["msgid"] = value
            elif field_no == 2:
                out["up_seqid"] = value
            elif field_no == 3:
                out["down_seqid"] = value
            elif field_no == 4:
                out["total_pack_count"] = value
            elif field_no == 5:
                out["current_pack_index"] = value
            elif field_no == 6:
                out["is_compress"] = bool(value)
            elif field_no == 7:
                out["checksum"] = value
    except Exception as exc:
        out["parse_error"] = str(exc)
    return out


def parse_sc_login(data: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field_no, wire, value in iter_fields(data):
        if wire == 2 and isinstance(value, bytes):
            if field_no == 1:
                out["uid"] = value.decode("utf-8", errors="replace")
            elif field_no == 2:
                out["login_token"] = value.decode("utf-8", errors="replace")
            elif field_no == 3:
                out["session_key_encrypted"] = bytes(value)
            elif field_no == 4:
                out["session_nonce"] = bytes(value)
        elif wire == 0 and isinstance(value, int):
            if field_no == 8:
                out["server_time"] = value
            elif field_no == 10:
                out["server_zone"] = value
    return out


def _import_private_key_from_b64_lines(data_lines: list[str]):
    if not data_lines:
        raise ValueError("private key not found")
    pem = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(data_lines) + "\n-----END PRIVATE KEY-----\n"
    try:
        return RSA.import_key(pem)
    except ValueError:
        pem = "-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(data_lines) + "\n-----END RSA PRIVATE KEY-----\n"
        return RSA.import_key(pem)


def load_private_key_from_txt(path: Path | None):
    if path is not None and path.exists():
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    elif CLIENT_NET_RSA_PRIVATE_KEY_B64:
        lines = ["=== CLIENT_NET_RSA_PRIVATE_KEY ===", *CLIENT_NET_RSA_PRIVATE_KEY_B64.splitlines(), "=== END ==="]
    else:
        raise FileNotFoundError(
            "rsa_keys.txt not found and embedded_keys.py is unavailable; provide an external rsa_keys.txt"
        )
    capture = False
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("=== CLIENT_NET_RSA_PRIVATE_KEY"):
            capture = True
            continue
        if line.startswith("===") and capture:
            break
        if capture and line.strip():
            data_lines.append(line.strip())
    try:
        return _import_private_key_from_b64_lines(data_lines)
    except ValueError:
        if path is None or not path.exists() or not CLIENT_NET_RSA_PRIVATE_KEY_B64:
            raise
    return _import_private_key_from_b64_lines(CLIENT_NET_RSA_PRIVATE_KEY_B64.splitlines())


def rsa_decrypt_session_key(private_key, encrypted_key: bytes) -> bytes:
    plain = PKCS1_v1_5.new(private_key).decrypt(encrypted_key, b"")
    if len(plain) != 32:
        raise RuntimeError(f"failed to decrypt session key: decrypted_len={len(plain)}")
    return plain


def pop_frame(buffer: bytearray) -> tuple[int, bytes, bytes] | None:
    if len(buffer) < 3:
        return None
    head_len = buffer[0]
    body_len = int.from_bytes(buffer[1:3], "little")
    end = 3 + head_len + body_len
    if end > len(buffer):
        return None
    head = bytes(buffer[3 : 3 + head_len])
    payload = bytes(buffer[3 + head_len : end])
    del buffer[:end]
    return head_len, head, payload


def iter_merged_frames(data: bytes) -> Iterator[tuple[int, int, bytes, bytes]]:
    offset = 0
    while offset + 3 <= len(data):
        head_len = data[offset]
        body_len = int.from_bytes(data[offset + 1 : offset + 3], "little")
        start = offset + 3
        end = start + head_len + body_len
        if end > len(data):
            break
        head = data[start : start + head_len]
        body = data[start + head_len : end]
        yield offset, head_len, head, body
        offset = end


def lz4_decompress_block(data: bytes) -> bytes:
    if not data:
        return b""
    source = memoryview(data)
    source_len = len(source)
    source_index = 0
    out = bytearray()
    while source_index < source_len:
        token = int(source[source_index])
        source_index += 1
        literal_len = token >> 4
        if literal_len == 15:
            while True:
                if source_index >= source_len:
                    raise ValueError("lz4 literal length overflow")
                extra = int(source[source_index])
                source_index += 1
                literal_len += extra
                if extra != 0xFF:
                    break
        literal_end = source_index + literal_len
        if literal_end > source_len:
            raise ValueError("lz4 literal overflow")
        out.extend(source[source_index:literal_end])
        source_index = literal_end
        if source_index >= source_len:
            break
        if source_index + 2 > source_len:
            raise ValueError("lz4 missing match offset")
        offset = int(source[source_index]) | (int(source[source_index + 1]) << 8)
        source_index += 2
        if offset <= 0 or offset > len(out):
            raise ValueError("lz4 invalid match offset")
        match_len = token & 0x0F
        if match_len == 15:
            while True:
                if source_index >= source_len:
                    raise ValueError("lz4 match length overflow")
                extra = int(source[source_index])
                source_index += 1
                match_len += extra
                if extra != 0xFF:
                    break
        match_len += 4
        while match_len > 0:
            chunk_len = min(match_len, offset)
            chunk_start = len(out) - offset
            chunk = out[chunk_start : chunk_start + chunk_len]
            if not chunk:
                raise ValueError("lz4 empty match chunk")
            out.extend(chunk)
            match_len -= len(chunk)
    return bytes(out)


def maybe_decompress_session_body(head: dict[str, Any], body: bytes) -> bytes:
    if not bool(head.get("is_compress")) or not body:
        return body
    for decoder in (
        lz4_decompress_block,
        zlib.decompress,
        lambda raw: zlib.decompress(raw, -zlib.MAX_WBITS),
        lambda raw: zlib.decompress(raw, zlib.MAX_WBITS | 16),
    ):
        try:
            return decoder(body)
        except Exception:
            continue
    return body
