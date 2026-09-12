"""
Upload allowlist, checked against the file's real bytes rather than its name.

An extension is a claim, not evidence: renaming `payload.exe` to `notes.pdf`
gets past any extension check. After the browser has uploaded to the bucket we
read the first few bytes back and confirm they match the declared type, so the
archive can never end up serving an executable as a PDF.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FileType:
    extension: str
    mime: str
    label: str
    # Alternative signatures, any one of which proves the type. Each is itself
    # a tuple of (offset, prefix) pairs that must ALL match, because some
    # formats are identified by two separated markers. Empty means the format
    # has no signature (plain text), so only the size is checked.
    signatures: tuple[tuple[tuple[int, bytes], ...], ...] = field(default=())


# Office formats since 2007 are ZIP containers, so pptx/docx/xlsx all share the
# ZIP signature. That is as far as magic bytes can distinguish them, and it is
# enough for the purpose here: proving the upload is not an executable.
_ZIP = (((0, b"PK\x03\x04"),), ((0, b"PK\x05\x06"),), ((0, b"PK\x07\x08"),))
# Pre-2007 Office files are OLE compound documents.
_OLE = (((0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),),)

ALLOWED: tuple[FileType, ...] = (
    FileType("pdf", "application/pdf", "PDF", (((0, b"%PDF-"),),)),
    FileType(
        "pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "PowerPoint",
        _ZIP,
    ),
    FileType(
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Word",
        _ZIP,
    ),
    FileType(
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Excel",
        _ZIP,
    ),
    FileType("ppt", "application/vnd.ms-powerpoint", "PowerPoint (legacy)", _OLE),
    FileType("doc", "application/msword", "Word (legacy)", _OLE),
    FileType("xls", "application/vnd.ms-excel", "Excel (legacy)", _OLE),
    FileType("zip", "application/zip", "ZIP archive", _ZIP),
    FileType("png", "image/png", "PNG image", (((0, b"\x89PNG\r\n\x1a\n"),),)),
    FileType("jpg", "image/jpeg", "JPEG image", (((0, b"\xff\xd8\xff"),),)),
    FileType("jpeg", "image/jpeg", "JPEG image", (((0, b"\xff\xd8\xff"),),)),
    FileType("gif", "image/gif", "GIF image", (((0, b"GIF87a"),), ((0, b"GIF89a"),))),
    FileType("webp", "image/webp", "WebP image", (((0, b"RIFF"), (8, b"WEBP")),)),
    FileType("txt", "text/plain", "Text", ()),
    FileType("md", "text/markdown", "Markdown", ()),
)

BY_EXTENSION = {ft.extension: ft for ft in ALLOWED}
ALLOWED_EXTENSIONS = tuple(BY_EXTENSION)

# Longest signature end offset; how many bytes we need to read back to verify.
SNIFF_BYTES = max(
    (
        offset + len(prefix)
        for ft in ALLOWED
        for alternative in ft.signatures
        for offset, prefix in alternative
    ),
    default=16,
)


def extension_of(filename: str) -> str:
    _, _, ext = (filename or "").rpartition(".")
    return ext.lower()


def lookup(filename: str) -> FileType | None:
    """The allowlist entry for this filename, or None if the type is not allowed."""
    return BY_EXTENSION.get(extension_of(filename))


def signature_matches(file_type: FileType, head: bytes) -> bool:
    """Whether `head` (the file's first SNIFF_BYTES bytes) looks like this type."""
    if not file_type.signatures:
        return True
    return any(
        all(head[offset : offset + len(prefix)] == prefix for offset, prefix in alternative)
        for alternative in file_type.signatures
    )
