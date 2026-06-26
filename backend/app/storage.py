"""Encrypted local file storage for the Smart Box.

Files are written under STORAGE_ROOT in the layout:
    {STORAGE_ROOT}/uploads/company_{company_id}/{year}/{month}/{uuid}_{filename}

Each file is encrypted with AES-256-GCM (see app.crypto) before being written,
so the bytes on disk are unintelligible without the master key.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import aiofiles

from app.config import settings
from app.crypto import decrypt_bytes, encrypt_bytes

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-\u0600-\u06FF]+")


def sanitize_filename(name: str) -> str:
    """Strip path separators / unsafe characters from an uploaded filename."""
    name = os.path.basename(name or "file")
    name = name.replace("\x00", "")
    name = _SAFE_NAME.sub("_", name).strip("._") or "file"
    return name[:200]


def build_relative_path(company_id: str, file_uuid: str, filename: str) -> str:
    """Return the storage-relative path (without STORAGE_ROOT prefix)."""
    now = datetime.now(timezone.utc)
    safe = sanitize_filename(filename)
    return os.path.join(
        "uploads",
        f"company_{company_id}",
        f"{now.year:04d}",
        f"{now.month:02d}",
        f"{file_uuid}_{safe}",
    )


def absolute_path(relative_path: str) -> str:
    return os.path.join(settings.STORAGE_ROOT, relative_path)


async def save_encrypted(
    *,
    plaintext: bytes,
    company_id: str,
    file_uuid: str,
    filename: str,
) -> str:
    """Encrypt and persist a file. Returns the storage-relative file path."""
    rel = build_relative_path(company_id, file_uuid, filename)
    abs_path = absolute_path(rel)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    blob = encrypt_bytes(
        plaintext,
        master_key=settings.ENCRYPTION_MASTER_KEY,
        company_id=company_id,
        file_uuid=file_uuid,
    )
    async with aiofiles.open(abs_path, "wb") as f:
        await f.write(blob)
    # Restrict permissions: owner read/write only.
    try:
        os.chmod(abs_path, 0o600)
    except OSError:
        pass
    return rel


async def load_decrypted(
    *,
    relative_path: str,
    company_id: str,
    file_uuid: str,
) -> bytes:
    """Read and decrypt a stored file back to plaintext."""
    abs_path = absolute_path(relative_path)
    async with aiofiles.open(abs_path, "rb") as f:
        blob = await f.read()
    return decrypt_bytes(
        blob,
        master_key=settings.ENCRYPTION_MASTER_KEY,
        company_id=company_id,
        file_uuid=file_uuid,
    )
