"""Windows DPAPI 加密工具：用于加密存储 API Key 等敏感设置。

用法：
- encrypt_str(明文) -> 密文（前缀 enc:）
- decrypt_str(值)   -> 明文（兼容未加密的旧数据；密文解密失败返回空串）
存储格式："enc:" + base64(CryptProtectData 输出)。
"""

import base64
import ctypes
import ctypes.wintypes

PREFIX = "enc:"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _protect(data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise RuntimeError(f"CryptProtectData failed: {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _unprotect(data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise RuntimeError(f"CryptUnprotectData failed: {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt_str(plain: str) -> str:
    if not plain:
        return plain
    try:
        return PREFIX + base64.b64encode(_protect(plain.encode("utf-8"))).decode("ascii")
    except Exception:
        # 加密失败（如非 Windows 环境）回退明文，保证可用性
        return plain


def decrypt_str(value) -> str:
    if not is_encrypted(value):
        return value or ""
    try:
        raw = base64.b64decode(value[len(PREFIX):])
        return _unprotect(raw).decode("utf-8")
    except Exception:
        return ""