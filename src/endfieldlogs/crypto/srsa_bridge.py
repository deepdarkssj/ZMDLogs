from __future__ import annotations

import ctypes
import os
from pathlib import Path

SRSA_MAGIC = b"\x05\x0f\x09\x0c"

C_GET = 0x8F6650A485
C_RET = 0x0F91A4399A0
C_SET = 0x971AB5C8FF
HANDLE_MIN = 0x100000
MAX_LEN = 0x100000


class SRSABridgeError(Exception):
    pass


class SRSABridge:
    def __init__(self, dll_dir: Path) -> None:
        self.dll_dir = Path(str(dll_dir).strip('"').strip("'")).resolve()
        try:
            os.add_dll_directory(str(self.dll_dir))
        except (AttributeError, OSError, ValueError):
            pass

        self._dll = ctypes.WinDLL(str(self.dll_dir / "GameAssembly.dll"))

        self._get_ver = self._dll.mono_method_h_get_ver
        self._get_ver.argtypes = []
        self._get_ver.restype = ctypes.c_uint64

        self._get_code = self._dll.mono_method_h_get_code
        self._get_code.argtypes = [ctypes.c_uint64, ctypes.c_uint32]
        self._get_code.restype = ctypes.c_uint64

        self._set_code = self._dll.mono_method_h_set_code
        self._set_code.argtypes = [ctypes.c_uint64]
        self._set_code.restype = ctypes.c_uint64

        self._remove_code = self._dll.mono_method_h_remove_code
        self._remove_code.argtypes = [ctypes.c_uint64]
        self._remove_code.restype = None

    @property
    def version(self) -> int:
        return int(self._get_ver())

    def decrypt_login_body(self, encrypted_body: bytes) -> bytes:
        src = (ctypes.c_ubyte * len(encrypted_body)).from_buffer_copy(encrypted_body)
        ptr = ctypes.cast(src, ctypes.c_void_p).value
        if ptr is None:
            raise SRSABridgeError("decrypt ptr is null")

        handle = self._set_code(ptr ^ C_SET)
        if handle < HANDLE_MIN:
            raise SRSABridgeError(f"mono_method_h_set_code failed code={handle}")

        try:
            decoded_ptr = handle ^ C_RET
            out_len = ctypes.c_int32.from_address(decoded_ptr).value
            if out_len < 0 or out_len > MAX_LEN:
                raise SRSABridgeError(f"decrypt out_len invalid: {out_len}")
            return ctypes.string_at(decoded_ptr + 4, out_len)
        finally:
            self._remove_code(handle)
