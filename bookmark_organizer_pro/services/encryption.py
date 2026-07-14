"""Versioned AES-256-GCM encrypted storage with recovery-key support.

Versions 1 and 2 use the historical PBKDF2-HMAC-SHA256 envelope.  New files
use Argon2id and authenticate the serialized KDF parameters as part of the
AES-GCM associated data.  Version 4 adds an independently encrypted recovery
copy of the plaintext.
"""

from __future__ import annotations

import importlib
import os
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bookmark_organizer_pro.logging_config import log


MAGIC = b"BOPC"
VERSION = 1
VERSION_RECOVERY = 2
VERSION_ARGON2 = 3
VERSION_ARGON2_RECOVERY = 4
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32
PBKDF2_ITERS = 480_000
RECOVERY_KEY_BYTES = 32

# Argon2 memory_cost is expressed in KiB.  Bounds are deliberately narrow so
# attacker-controlled headers cannot turn decryption into resource exhaustion.
ARGON2_MEMORY_KIB = 64 * 1024
ARGON2_ITERATIONS = 3
ARGON2_LANES = 4
ARGON2_MIN_MEMORY_KIB = 19 * 1024
ARGON2_MAX_MEMORY_KIB = 256 * 1024
ARGON2_MAX_ITERATIONS = 10
ARGON2_MAX_LANES = 16


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _fd_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
        return False
    except OSError:
        return True


def _read_u32(blob: bytes, offset: int, label: str) -> tuple[int, int]:
    if offset + 4 > len(blob):
        raise ValueError(f"Truncated encrypted file: missing {label}")
    return struct.unpack_from(">I", blob, offset)[0], offset + 4


def _read_bytes(blob: bytes, offset: int, length: int, label: str) -> tuple[bytes, int]:
    if length < 0 or offset + length > len(blob):
        raise ValueError(f"Truncated encrypted file: missing {label}")
    return blob[offset:offset + length], offset + length


def _validate_argon2_params(memory_kib: int, iterations: int, lanes: int) -> None:
    if not ARGON2_MIN_MEMORY_KIB <= memory_kib <= ARGON2_MAX_MEMORY_KIB:
        raise ValueError("Invalid Argon2id memory cost")
    if not 1 <= iterations <= ARGON2_MAX_ITERATIONS:
        raise ValueError("Invalid Argon2id iteration count")
    if not 1 <= lanes <= ARGON2_MAX_LANES:
        raise ValueError("Invalid Argon2id lane count")
    if memory_kib < 8 * lanes:
        raise ValueError("Invalid Argon2id memory/lane combination")


def _atomic_write(path: Path, payload: bytes) -> None:
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.resolve().parent, suffix=".tmp")
    try:
        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        if not _fd_closed(fd):
            os.close(fd)
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


class CryptoUnavailable(RuntimeError):
    pass


def generate_recovery_key() -> str:
    """Generate a human-readable recovery key (base32-encoded, 256-bit)."""
    import base64

    return base64.b32encode(os.urandom(RECOVERY_KEY_BYTES)).decode("ascii").rstrip("=")


def _recovery_key_to_bytes(key_str: str) -> bytes:
    import base64

    try:
        padded = key_str.strip().upper() + "=" * (-len(key_str.strip()) % 8)
        decoded = base64.b32decode(padded, casefold=True)
    except Exception as exc:
        raise ValueError("Invalid recovery key") from exc
    if len(decoded) != RECOVERY_KEY_BYTES:
        raise ValueError("Invalid recovery key")
    return decoded


class EncryptedStore:
    """Encrypt and decrypt arbitrary bytes with a passphrase."""

    def __init__(self, passphrase: str):
        if not passphrase:
            raise ValueError("Passphrase required")
        self._passphrase = bytearray(passphrase.encode("utf-8"))

    def close(self):
        if hasattr(self, "_passphrase") and self._passphrase:
            for i in range(len(self._passphrase)):
                self._passphrase[i] = 0
            self._passphrase = bytearray()

    def __del__(self):
        self.close()

    @staticmethod
    def available() -> bool:
        return _try_import("cryptography") is not None

    @staticmethod
    def _derive_pbkdf2(secret: bytes | bytearray, salt: bytes) -> bytes:
        pbkdf2 = _try_import("cryptography.hazmat.primitives.kdf.pbkdf2")
        hashes = _try_import("cryptography.hazmat.primitives.hashes")
        if pbkdf2 is None or hashes is None:
            raise CryptoUnavailable("Install `cryptography` to use encrypted storage")
        return pbkdf2.PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=KEY_LEN, salt=salt,
            iterations=PBKDF2_ITERS,
        ).derive(secret)

    @staticmethod
    def _derive_argon2(
        secret: bytes | bytearray,
        salt: bytes,
        memory_kib: int,
        iterations: int,
        lanes: int,
    ) -> bytes:
        _validate_argon2_params(memory_kib, iterations, lanes)
        argon2 = _try_import("cryptography.hazmat.primitives.kdf.argon2")
        if argon2 is None:
            raise CryptoUnavailable("Install `cryptography>=44` to use Argon2id encrypted storage")
        return argon2.Argon2id(
            salt=salt,
            length=KEY_LEN,
            iterations=iterations,
            lanes=lanes,
            memory_cost=memory_kib,
        ).derive(secret)

    @staticmethod
    def _ciphers():
        ciphers = _try_import("cryptography.hazmat.primitives.ciphers.aead")
        if ciphers is None:
            raise CryptoUnavailable("Install `cryptography` to use encrypted storage")
        return ciphers

    @staticmethod
    def format_version(blob: bytes) -> int:
        if not blob.startswith(MAGIC):
            raise ValueError("Not an encrypted bookmark file")
        version, _ = _read_u32(blob, len(MAGIC), "format version")
        return version

    @staticmethod
    def _argon_header(version: int, salt: bytes, nonce: bytes) -> bytes:
        return (
            MAGIC
            + struct.pack(">IIII", version, ARGON2_MEMORY_KIB, ARGON2_ITERATIONS, ARGON2_LANES)
            + salt
            + nonce
        )

    def encrypt(self, plaintext: bytes) -> bytes:
        salt = os.urandom(SALT_LEN)
        nonce = os.urandom(NONCE_LEN)
        header = self._argon_header(VERSION_ARGON2, salt, nonce)
        key = self._derive_argon2(
            self._passphrase, salt, ARGON2_MEMORY_KIB, ARGON2_ITERATIONS, ARGON2_LANES,
        )
        ct = self._ciphers().AESGCM(key).encrypt(nonce, plaintext, header)
        return header + struct.pack(">I", len(ct)) + ct

    @staticmethod
    def _parse_legacy_primary(blob: bytes, offset: int) -> tuple[bytes, bytes, bytes, int]:
        salt, offset = _read_bytes(blob, offset, SALT_LEN, "salt")
        nonce, offset = _read_bytes(blob, offset, NONCE_LEN, "nonce")
        ct_len, offset = _read_u32(blob, offset, "ciphertext length")
        ct, offset = _read_bytes(blob, offset, ct_len, "ciphertext")
        return salt, nonce, ct, offset

    @staticmethod
    def _parse_argon_primary(
        blob: bytes, offset: int, version: int,
    ) -> tuple[int, int, int, bytes, bytes, bytes, bytes, int]:
        memory_kib, offset = _read_u32(blob, offset, "Argon2id memory cost")
        iterations, offset = _read_u32(blob, offset, "Argon2id iteration count")
        lanes, offset = _read_u32(blob, offset, "Argon2id lane count")
        _validate_argon2_params(memory_kib, iterations, lanes)
        salt, offset = _read_bytes(blob, offset, SALT_LEN, "salt")
        nonce, offset = _read_bytes(blob, offset, NONCE_LEN, "nonce")
        header = blob[:offset]
        ct_len, offset = _read_u32(blob, offset, "ciphertext length")
        ct, offset = _read_bytes(blob, offset, ct_len, "ciphertext")
        expected = MAGIC + struct.pack(">I", version)
        if not header.startswith(expected):
            raise ValueError("Invalid encrypted file header")
        return memory_kib, iterations, lanes, salt, nonce, header, ct, offset

    def decrypt(self, blob: bytes) -> bytes:
        version = self.format_version(blob)
        offset = len(MAGIC) + 4
        if version in (VERSION, VERSION_RECOVERY):
            salt, nonce, ct, offset = self._parse_legacy_primary(blob, offset)
            if version == VERSION and offset != len(blob):
                raise ValueError("Invalid trailing data in encrypted file")
            if version == VERSION_RECOVERY:
                self._parse_recovery_record(blob, offset)
            key = self._derive_pbkdf2(self._passphrase, salt)
            return self._ciphers().AESGCM(key).decrypt(nonce, ct, MAGIC)
        if version not in (VERSION_ARGON2, VERSION_ARGON2_RECOVERY):
            raise ValueError(f"Unsupported encrypted file version {version}")
        memory_kib, iterations, lanes, salt, nonce, header, ct, offset = self._parse_argon_primary(
            blob, offset, version,
        )
        if version == VERSION_ARGON2 and offset != len(blob):
            raise ValueError("Invalid trailing data in encrypted file")
        if version == VERSION_ARGON2_RECOVERY:
            self._parse_recovery_record(blob, offset)
        key = self._derive_argon2(self._passphrase, salt, memory_kib, iterations, lanes)
        return self._ciphers().AESGCM(key).decrypt(nonce, ct, header)

    @staticmethod
    def _parse_recovery_record(blob: bytes, offset: int) -> tuple[bytes, bytes, bytes]:
        salt, offset = _read_bytes(blob, offset, SALT_LEN, "recovery salt")
        nonce, offset = _read_bytes(blob, offset, NONCE_LEN, "recovery nonce")
        ct_len, offset = _read_u32(blob, offset, "recovery ciphertext length")
        ct, offset = _read_bytes(blob, offset, ct_len, "recovery ciphertext")
        if offset != len(blob):
            raise ValueError("Invalid trailing data in encrypted file")
        return salt, nonce, ct

    def encrypt_with_recovery(self, plaintext: bytes, recovery_key: str) -> bytes:
        salt = os.urandom(SALT_LEN)
        nonce = os.urandom(NONCE_LEN)
        header = self._argon_header(VERSION_ARGON2_RECOVERY, salt, nonce)
        params = (ARGON2_MEMORY_KIB, ARGON2_ITERATIONS, ARGON2_LANES)
        key = self._derive_argon2(self._passphrase, salt, *params)
        ct = self._ciphers().AESGCM(key).encrypt(nonce, plaintext, header)

        recovery_salt = os.urandom(SALT_LEN)
        recovery_nonce = os.urandom(NONCE_LEN)
        recovery_secret = _recovery_key_to_bytes(recovery_key)
        recovery_key_bytes = self._derive_argon2(recovery_secret, recovery_salt, *params)
        recovery_aad = header + b"recovery" + recovery_salt + recovery_nonce
        recovery_ct = self._ciphers().AESGCM(recovery_key_bytes).encrypt(
            recovery_nonce, plaintext, recovery_aad,
        )
        return (
            header + struct.pack(">I", len(ct)) + ct
            + recovery_salt + recovery_nonce
            + struct.pack(">I", len(recovery_ct)) + recovery_ct
        )

    @staticmethod
    def decrypt_with_recovery_key(blob: bytes, recovery_key: str) -> bytes:
        version = EncryptedStore.format_version(blob)
        offset = len(MAGIC) + 4
        recovery_secret = _recovery_key_to_bytes(recovery_key)
        if version == VERSION_RECOVERY:
            _, _, _, offset = EncryptedStore._parse_legacy_primary(blob, offset)
            salt, nonce, ct = EncryptedStore._parse_recovery_record(blob, offset)
            key = EncryptedStore._derive_pbkdf2(recovery_secret, salt)
            return EncryptedStore._ciphers().AESGCM(key).decrypt(nonce, ct, MAGIC)
        if version != VERSION_ARGON2_RECOVERY:
            raise ValueError("File does not contain a recovery key")
        memory_kib, iterations, lanes, _, _, header, _, offset = EncryptedStore._parse_argon_primary(
            blob, offset, version,
        )
        salt, nonce, ct = EncryptedStore._parse_recovery_record(blob, offset)
        key = EncryptedStore._derive_argon2(
            recovery_secret, salt, memory_kib, iterations, lanes,
        )
        recovery_aad = header + b"recovery" + salt + nonce
        return EncryptedStore._ciphers().AESGCM(key).decrypt(nonce, ct, recovery_aad)

    def encrypt_file(self, src: Path, dst: Optional[Path] = None) -> Path:
        dst = dst or src.with_suffix(src.suffix + ".enc")
        _atomic_write(dst, self.encrypt(src.read_bytes()))
        return dst

    def decrypt_file(self, src: Path, dst: Optional[Path] = None) -> Path:
        dst = dst or src.with_suffix("")
        if dst.resolve() == src.resolve():
            raise ValueError("Destination must differ from source")
        _atomic_write(dst, self.decrypt(src.read_bytes()))
        return dst

    @staticmethod
    def decrypt_recovery_file(src: Path, recovery_key: str, dst: Path | None = None) -> Path:
        """Decrypt a recovery-bearing file without exposing a partial output."""
        dst = dst or src.with_suffix("")
        if dst.resolve() == src.resolve():
            raise ValueError("Destination must differ from source")
        plaintext = EncryptedStore.decrypt_with_recovery_key(src.read_bytes(), recovery_key)
        _atomic_write(dst, plaintext)
        return dst

    def is_encrypted(self, path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                return handle.read(len(MAGIC)) == MAGIC
        except OSError:
            return False

    @staticmethod
    def rotate_passphrase(
        path: Path,
        old_passphrase: str,
        new_passphrase: str,
        recovery_key: str | None = None,
    ) -> bool:
        """Rotate a passphrase only after creating and verifying a byte-exact backup.

        Recovery-bearing files require their recovery key so rotation cannot
        silently discard emergency access.
        """
        try:
            original = path.read_bytes()
            version = EncryptedStore.format_version(original)
            has_recovery = version in (VERSION_RECOVERY, VERSION_ARGON2_RECOVERY)
            old_store = EncryptedStore(old_passphrase)
            plaintext = old_store.decrypt(original)
            if has_recovery:
                if not recovery_key:
                    raise ValueError("Recovery key required to preserve recovery access")
                recovered = EncryptedStore.decrypt_with_recovery_key(original, recovery_key)
                if recovered != plaintext:
                    raise ValueError("Recovery key verification failed")

            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = path.with_name(f"{path.name}.pre-rotation-{stamp}.bak")
            _atomic_write(backup, original)
            if backup.read_bytes() != original:
                raise OSError("Pre-rotation backup verification failed")

            new_store = EncryptedStore(new_passphrase)
            new_blob = (
                new_store.encrypt_with_recovery(plaintext, recovery_key)
                if has_recovery and recovery_key
                else new_store.encrypt(plaintext)
            )
            if new_store.decrypt(new_blob) != plaintext:
                raise ValueError("Rotated encrypted file verification failed")
            if has_recovery and EncryptedStore.decrypt_with_recovery_key(new_blob, recovery_key) != plaintext:
                raise ValueError("Rotated recovery copy verification failed")
            _atomic_write(path, new_blob)
            log.info("Passphrase rotated for %s after verified backup %s", path.name, backup.name)
            return True
        except Exception as exc:
            log.error("Passphrase rotation failed for %s: %s", path.name, exc)
            return False
