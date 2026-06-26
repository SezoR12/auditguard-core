"""Upload validation: extension allow-list + MIME/extension consistency check.

Uses python-magic (libmagic) to sniff the real content type from the file bytes
and rejects files whose true type does not match their extension — this catches
e.g. an .exe renamed to .pdf (the "virus scan simulation").
"""
from __future__ import annotations

import magic

from app.models.enums import FileType

# extension -> logical FileType
EXT_TO_FILETYPE: dict[str, FileType] = {
    ".xlsx": FileType.excel,
    ".xls": FileType.excel,
    ".csv": FileType.csv,
    ".docx": FileType.word,
    ".doc": FileType.word,
    ".jpg": FileType.image,
    ".jpeg": FileType.image,
    ".png": FileType.image,
    ".tiff": FileType.image,
    ".tif": FileType.image,
    ".pdf": FileType.pdf,
    ".json": FileType.encrypted_json,  # JSON is treated as the encrypted-JSON pipeline
}

ALLOWED_EXTENSIONS = set(EXT_TO_FILETYPE.keys())

# Acceptable detected MIME types per extension. libmagic can be picky, so we
# allow a small set of equivalents per format.
EXT_TO_MIMES: dict[str, set[str]] = {
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",  # OOXML is a zip container
        "application/octet-stream",
    },
    ".xls": {"application/vnd.ms-excel", "application/x-ole-storage", "application/octet-stream"},
    ".csv": {"text/csv", "text/plain", "application/csv", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".doc": {"application/msword", "application/x-ole-storage", "application/octet-stream"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".tiff": {"image/tiff"},
    ".tif": {"image/tiff"},
    ".pdf": {"application/pdf"},
    ".json": {"application/json", "text/plain", "text/json", "application/octet-stream"},
}


def detect_mime(data: bytes) -> str:
    """Return the MIME type sniffed from the file content."""
    return magic.from_buffer(data, mime=True)


def extension_of(filename: str) -> str:
    name = (filename or "").lower()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def validate_upload(filename: str, data: bytes) -> tuple[FileType, str]:
    """Validate extension and that the sniffed MIME matches.

    Returns (FileType, detected_mime). Raises ValueError on a problem; the API
    layer converts that into an HTTP 400 with an Arabic message.
    """
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("extension_not_allowed")

    detected = detect_mime(data)
    allowed_mimes = EXT_TO_MIMES.get(ext, set())
    if detected not in allowed_mimes:
        raise ValueError(f"mime_mismatch:{detected}")

    return EXT_TO_FILETYPE[ext], detected
