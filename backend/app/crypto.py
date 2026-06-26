"""File-at-rest encryption using AES-256-GCM.

Design:
- A per-file data-encryption key (DEK) is DERIVED on the fly from the
  ENCRYPTION_MASTER_KEY (env) + company_id + file UUID using HKDF-SHA256.
- The DEK is NEVER stored anywhere (not in the DB, not on disk).
- A random 16-byte salt and 12-byte nonce are generated per file and stored
  in a small plaintext header prepended to the ciphertext. Salt and nonce are
  NOT secret; only the master key is.

On-disk file layout (all binary, concatenated):
    magic   : 5 bytes  b"AGEC1"      (AuditCore Encrypted, v1)
    version : 1 byte    0x01
    salt    : 16 bytes
    nonce   : 12 bytes
    ciphertext+tag : remainder (GCM tag is appended by AESGCM.encrypt)
"""
from __future__ import annotations

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"AGEC1"
VERSION = 1
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32  # AES-256

HEADER_LEN = len(MAGIC) + 1 + SALT_LEN + NONCE_LEN


def _derive_key(master_key: str, company_id: str, file_uuid: str, salt: bytes) -> bytes:
    """Derive a 32-byte per-file key from the master key + context, via HKDF."""
    info = f"auditcore|company={company_id}|file={file_uuid}".encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=salt,
        info=info,
    )
    return hkdf.derive(master_key.encode("utf-8"))


def encrypt_bytes(
    plaintext: bytes,
    *,
    master_key: str,
    company_id: str,
    file_uuid: str,
) -> bytes:
    """Encrypt plaintext and return the full on-disk blob (header + ciphertext)."""
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive_key(master_key, company_id, file_uuid, salt)
    aad = f"{company_id}:{file_uuid}".encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return MAGIC + bytes([VERSION]) + salt + nonce + ciphertext


def decrypt_bytes(
    blob: bytes,
    *,
    master_key: str,
    company_id: str,
    file_uuid: str,
) -> bytes:
    """Reverse of encrypt_bytes. Raises ValueError on a malformed/tampered file."""
    if len(blob) < HEADER_LEN or blob[: len(MAGIC)] != MAGIC:
        raise ValueError("Not an AuditCore encrypted file (bad magic).")
    offset = len(MAGIC)
    version = blob[offset]
    offset += 1
    if version != VERSION:
        raise ValueError(f"Unsupported encryption version: {version}")
    salt = blob[offset : offset + SALT_LEN]
    offset += SALT_LEN
    nonce = blob[offset : offset + NONCE_LEN]
    offset += NONCE_LEN
    ciphertext = blob[offset:]
    key = _derive_key(master_key, company_id, file_uuid, salt)
    aad = f"{company_id}:{file_uuid}".encode("utf-8")
    return AESGCM(key).decrypt(nonce, ciphertext, aad)
