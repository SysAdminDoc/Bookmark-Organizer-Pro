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
from typing import Optional

from bookmark_organizer_pro.logging_config import log


MAGIC = b"BOPC"
VERSION = 1
VERSION_RECOVERY = 2
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32  # 256-bit
PBKDF2_ITERS = 480_000
RECOVERY_KEY_BYTES = 32


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _fd_closed(fd: int) -> bool:
    """Check if a file descriptor was already closed."""
    try:
        os.fstat(fd)
        return False
    except OSError:
        return True


class CryptoUnavailable(RuntimeError):
    pass


def generate_recovery_key() -> str:
    """Generate a human-readable recovery key (base32-encoded, 256-bit)."""
    import base64
    raw = os.urandom(RECOVERY_KEY_BYTES)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _recovery_key_to_bytes(key_str: str) -> bytes:
    """Decode a base32 recovery key string back to raw bytes."""
    import base64
    padded = key_str + "=" * (-len(key_str) % 8)
    return base64.b32decode(padded)


class EncryptedStore:
    """Encrypt/decrypt arbitrary bytes with a passphrase."""

    def __init__(self, passphrase: str):
        if not passphrase:
            raise ValueError("Passphrase required")
        self._passphrase = bytearray(passphrase.encode("utf-8"))

    def close(self):
        """Wipe the passphrase material from memory."""
        if hasattr(self, "_passphrase") and self._passphrase:
            for i in range(len(self._passphrase)):
                self._passphrase[i] = 0
            self._passphrase = bytearray()

    def __del__(self):
        self.close()

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
        if version not in (VERSION, VERSION_RECOVERY):
            raise ValueError(f"Unsupported encrypted file version {version}")
        salt = blob[offset:offset + SALT_LEN]; offset += SALT_LEN
        nonce = blob[offset:offset + NONCE_LEN]; offset += NONCE_LEN
        (ct_len,) = struct.unpack(">I", blob[offset:offset + 4]); offset += 4
        if offset + ct_len > len(blob):
            raise ValueError("Truncated encrypted file: ciphertext length exceeds available data")
        ct = blob[offset:offset + ct_len]
        key = self._derive(salt)
        aes = ciphers.AESGCM(key)
        return aes.decrypt(nonce, ct, MAGIC)

    def encrypt_with_recovery(self, plaintext: bytes, recovery_key: str) -> bytes:
        """Encrypt with both passphrase and recovery key (version 2 format).

        Format: MAGIC + version(2) + salt + nonce + ct_len + ct +
                recovery_salt + recovery_nonce + recovery_ct_len + recovery_ct
        Both the passphrase and recovery key independently encrypt the same plaintext.
        """
        ciphers = _try_import("cryptography.hazmat.primitives.ciphers.aead")
        if ciphers is None:
            raise CryptoUnavailable("Install `cryptography` to use encrypted storage")
        salt = os.urandom(SALT_LEN)
        nonce = os.urandom(NONCE_LEN)
        key = self._derive(salt)
        aes = ciphers.AESGCM(key)
        ct = aes.encrypt(nonce, plaintext, MAGIC)

        rk_bytes = _recovery_key_to_bytes(recovery_key)
        rk_salt = os.urandom(SALT_LEN)
        rk_nonce = os.urandom(NONCE_LEN)
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives.hashes import SHA256
        rk_kdf = PBKDF2HMAC(algorithm=SHA256(), length=KEY_LEN, salt=rk_salt, iterations=PBKDF2_ITERS)
        rk_derived = rk_kdf.derive(rk_bytes)
        rk_aes = ciphers.AESGCM(rk_derived)
        rk_ct = rk_aes.encrypt(rk_nonce, plaintext, MAGIC)

        header = MAGIC + struct.pack(">I", VERSION_RECOVERY)
        primary = salt + nonce + struct.pack(">I", len(ct)) + ct
        recovery = rk_salt + rk_nonce + struct.pack(">I", len(rk_ct)) + rk_ct
        return header + primary + recovery

    @staticmethod
    def decrypt_with_recovery_key(blob: bytes, recovery_key: str) -> bytes:
        """Decrypt using a recovery key (version 2 format only)."""
        ciphers = _try_import("cryptography.hazmat.primitives.ciphers.aead")
        if ciphers is None:
            raise CryptoUnavailable("Install `cryptography` to use encrypted storage")
        if not blob.startswith(MAGIC):
            raise ValueError("Not an encrypted bookmark file")
        offset = len(MAGIC)
        (version,) = struct.unpack(">I", blob[offset:offset + 4])
        offset += 4
        if version != VERSION_RECOVERY:
            raise ValueError("File does not contain a recovery key (version 1 format)")
        blob[offset:offset + SALT_LEN]; offset += SALT_LEN
        blob[offset:offset + NONCE_LEN]; offset += NONCE_LEN
        (ct_len,) = struct.unpack(">I", blob[offset:offset + 4]); offset += 4
        offset += ct_len

        rk_salt = blob[offset:offset + SALT_LEN]; offset += SALT_LEN
        rk_nonce = blob[offset:offset + NONCE_LEN]; offset += NONCE_LEN
        (rk_ct_len,) = struct.unpack(">I", blob[offset:offset + 4]); offset += 4
        rk_ct = blob[offset:offset + rk_ct_len]

        rk_bytes = _recovery_key_to_bytes(recovery_key)
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives.hashes import SHA256
        rk_kdf = PBKDF2HMAC(algorithm=SHA256(), length=KEY_LEN, salt=rk_salt, iterations=PBKDF2_ITERS)
        rk_derived = rk_kdf.derive(rk_bytes)
        rk_aes = ciphers.AESGCM(rk_derived)
        return rk_aes.decrypt(rk_nonce, rk_ct, MAGIC)

    # ----- convenience file API -----
    def encrypt_file(self, src: Path, dst: Optional[Path] = None) -> Path:
        import tempfile
        dst = dst or src.with_suffix(src.suffix + ".enc")
        data = src.read_bytes()
        encrypted = self.encrypt(data)
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dst.resolve().parent, suffix=".tmp")
        try:
            os.write(fd, encrypted)
            os.close(fd)
            os.replace(tmp, dst)
        except Exception:
            os.close(fd) if not _fd_closed(fd) else None
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        return dst

    def decrypt_file(self, src: Path, dst: Optional[Path] = None) -> Path:
        import tempfile
        dst = dst or src.with_suffix("")
        if dst.resolve() == src.resolve():
            raise ValueError("Destination must differ from source")
        data = src.read_bytes()
        decrypted = self.decrypt(data)
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dst.resolve().parent, suffix=".tmp")
        try:
            os.write(fd, decrypted)
            os.close(fd)
            os.replace(tmp, dst)
        except Exception:
            os.close(fd) if not _fd_closed(fd) else None
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        return dst

    def is_encrypted(self, path: Path) -> bool:
        try:
            with path.open("rb") as f:
                return f.read(len(MAGIC)) == MAGIC
        except OSError:
            return False

    @staticmethod
    def rotate_passphrase(path: Path, old_passphrase: str,
                          new_passphrase: str) -> bool:
        """Re-encrypt a file with a new passphrase. Atomic write prevents corruption."""
        import tempfile
        try:
            old_store = EncryptedStore(old_passphrase)
            data = old_store.decrypt(path.read_bytes())
            new_store = EncryptedStore(new_passphrase)
            new_blob = new_store.encrypt(data)
            fd, tmp = tempfile.mkstemp(dir=path.resolve().parent, suffix=".tmp")
            try:
                os.write(fd, new_blob)
                os.close(fd)
                os.replace(tmp, path)
            except Exception:
                os.close(fd) if not _fd_closed(fd) else None
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise
            log.info(f"Passphrase rotated for {path.name} at {__import__('datetime').datetime.now().isoformat()}")
            return True
        except Exception as exc:
            log.error(f"Passphrase rotation failed for {path.name}: {exc}")
            return False
