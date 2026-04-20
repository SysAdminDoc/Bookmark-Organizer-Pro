"""Optional encrypted-storage layer (Buku-style toggle).

Wraps `master_bookmarks.json` (and any other JSON the user picks) with
authenticated AES-256-GCM. Uses PBKDF2-HMAC-SHA256 (480 000 iterations,
NIST SP 800-132 floor) to derive the key from a passphrase.

When enabled, the file on disk holds:
    [4-byte magic 'BOPC'][4-byte version=1][16-byte salt][12-byte nonce]
    [4-byte ciphertext length][ciphertext + 16-byte tag]

If the `cryptography` package is unavailable we degrade gracefully: writes
fail loudly so users can install the dep.
"""

from __future__ import annotations

import importlib
import os
import struct
from pathlib import Path
from typing import Optional, Tuple

from bookmark_organizer_pro.logging_config import log


MAGIC = b"BOPC"
VERSION = 1
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32  # 256-bit
PBKDF2_ITERS = 480_000


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


class CryptoUnavailable(RuntimeError):
    pass


class EncryptedStore:
    """Encrypt/decrypt arbitrary bytes with a passphrase."""

    def __init__(self, passphrase: str):
        if not passphrase:
            raise ValueError("Passphrase required")
        self._passphrase = passphrase.encode("utf-8")

    @staticmethod
    def available() -> bool:
        crypto = _try_import("cryptography")
        return crypto is not None

    def _derive(self, salt: bytes) -> bytes:
        crypto = _try_import("cryptography.hazmat.primitives.kdf.pbkdf2")
        hashes = _try_import("cryptography.hazmat.primitives.hashes")
        if crypto is None or hashes is None:
            raise CryptoUnavailable("Install `cryptography` to use encrypted storage")
        kdf = crypto.PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_LEN, salt=salt,
            iterations=PBKDF2_ITERS,
        )
        return kdf.derive(self._passphrase)

    def encrypt(self, plaintext: bytes) -> bytes:
        ciphers = _try_import("cryptography.hazmat.primitives.ciphers.aead")
        if ciphers is None:
            raise CryptoUnavailable("Install `cryptography` to use encrypted storage")
        salt = os.urandom(SALT_LEN)
        nonce = os.urandom(NONCE_LEN)
        key = self._derive(salt)
        aes = ciphers.AESGCM(key)
        ct = aes.encrypt(nonce, plaintext, MAGIC)
        return MAGIC + struct.pack(">I", VERSION) + salt + nonce + struct.pack(">I", len(ct)) + ct

    def decrypt(self, blob: bytes) -> bytes:
        ciphers = _try_import("cryptography.hazmat.primitives.ciphers.aead")
        if ciphers is None:
            raise CryptoUnavailable("Install `cryptography` to use encrypted storage")
        if not blob.startswith(MAGIC):
            raise ValueError("Not an encrypted bookmark file")
        offset = len(MAGIC)
        (version,) = struct.unpack(">I", blob[offset:offset + 4])
        offset += 4
        if version != VERSION:
            raise ValueError(f"Unsupported encrypted file version {version}")
        salt = blob[offset:offset + SALT_LEN]; offset += SALT_LEN
        nonce = blob[offset:offset + NONCE_LEN]; offset += NONCE_LEN
        (ct_len,) = struct.unpack(">I", blob[offset:offset + 4]); offset += 4
        ct = blob[offset:offset + ct_len]
        key = self._derive(salt)
        aes = ciphers.AESGCM(key)
        return aes.decrypt(nonce, ct, MAGIC)

    # ----- convenience file API -----
    def encrypt_file(self, src: Path, dst: Optional[Path] = None) -> Path:
        dst = dst or src.with_suffix(src.suffix + ".enc")
        data = src.read_bytes()
        dst.write_bytes(self.encrypt(data))
        return dst

    def decrypt_file(self, src: Path, dst: Optional[Path] = None) -> Path:
        dst = dst or src.with_suffix("")
        data = src.read_bytes()
        dst.write_bytes(self.decrypt(data))
        return dst

    def is_encrypted(self, path: Path) -> bool:
        try:
            with path.open("rb") as f:
                return f.read(len(MAGIC)) == MAGIC
        except OSError:
            return False
