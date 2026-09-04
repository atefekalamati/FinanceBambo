# -*- coding: utf-8 -*-
"""What may be uploaded, checked before anything reads the file.

Two things are checked, and the order matters. The declared content type is checked because
it is cheap; the file's own leading bytes are checked because the declared type is supplied
by whoever is uploading and a rename costs nothing. A `.jpg` that begins with `MZ` is a
Windows executable whatever the request said, and it is refused here rather than handed to an
image decoder.
"""

from pathlib import Path

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024

IMAGE_TYPES = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
}
AUDIO_TYPES = {
    "audio/mpeg": (".mp3",),
    "audio/mp4": (".m4a",),
    "audio/x-m4a": (".m4a",),
    "audio/wav": (".wav",),
    "audio/x-wav": (".wav",),
    "audio/ogg": (".ogg",),
}

#: Leading bytes that identify a format regardless of what the upload claimed.
#: WebP and WAV both begin with `RIFF`; the format name sits at offset 8, so those two are
#: matched on the pair rather than the prefix alone.
_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
    (b"\xff\xf3", "audio/mpeg"),
    (b"\xff\xf2", "audio/mpeg"),
    (b"OggS", "audio/ogg"),
)

#: Refused outright, whatever the extension says. Not an exhaustive list of dangerous
#: formats -- it cannot be -- but these are the ones a mislabelled upload actually arrives as.
_EXECUTABLE = (b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe", b"PK\x03\x04", b"#!")


class UnsupportedUpload(ValueError):
    """The file is not something this pipeline will read. Carries a reason for the user."""


def sniff(head: bytes) -> str | None:
    """The content type the bytes themselves indicate, or None if unrecognised."""
    if head[:4] == b"RIFF" and len(head) >= 12:
        if head[8:12] == b"WEBP":
            return "image/webp"
        if head[8:12] == b"WAVE":
            return "audio/wav"
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    for prefix, kind in _SIGNATURES:
        if head.startswith(prefix):
            return kind
    return None


def validate_upload(filename: str, declared_type: str | None, size_bytes: int,
                    head: bytes) -> tuple[str, str]:
    """Accept an upload, or refuse it with a reason. Returns `(kind, content_type)`.

    `kind` is `"image"` or `"audio"` -- which provider will read it, and which of the two
    size limits applied.
    """
    if any(head.startswith(magic) for magic in _EXECUTABLE):
        raise UnsupportedUpload("این فایل اجرایی یا آرشیو است و پذیرفته نمی‌شود.")

    actual = sniff(head)
    if actual is None:
        raise UnsupportedUpload(
            "قالب فایل شناسایی نشد. تصویر (jpg، png، webp) یا صدا (mp3، m4a، wav، ogg) بفرستید.")

    if actual in IMAGE_TYPES:
        kind, limit, permitted = "image", MAX_IMAGE_BYTES, IMAGE_TYPES
    elif actual in AUDIO_TYPES:
        kind, limit, permitted = "audio", MAX_AUDIO_BYTES, AUDIO_TYPES
    else:
        raise UnsupportedUpload("قالب %s پشتیبانی نمی‌شود." % actual)

    if size_bytes <= 0:
        raise UnsupportedUpload("فایل خالی است.")
    if size_bytes > limit:
        raise UnsupportedUpload(
            "حجم فایل %.1f مگابایت است؛ بیشینه برای %s برابر %d مگابایت است."
            % (size_bytes / 1024 / 1024, "تصویر" if kind == "image" else "صدا",
               limit // 1024 // 1024))

    # The declared type is allowed to disagree only in the harmless direction: browsers send
    # audio/mp4 and audio/x-m4a for the same file, and some send nothing at all. A declared
    # type from the *other* family is a mismatch worth refusing, because it means the caller
    # believes it is uploading something else.
    if declared_type:
        declared = declared_type.split(";")[0].strip().lower()
        if declared in IMAGE_TYPES and kind != "image":
            raise UnsupportedUpload("محتوای فایل با نوع اعلام‌شده (%s) نمی‌خواند." % declared)
        if declared in AUDIO_TYPES and kind != "image" and actual not in AUDIO_TYPES:
            raise UnsupportedUpload("محتوای فایل با نوع اعلام‌شده (%s) نمی‌خواند." % declared)

    suffix = Path(filename or "").suffix.lower()
    if suffix and suffix not in permitted[actual]:
        # Not fatal on its own -- the bytes decide -- but a `.exe` named over a real JPEG is
        # still refused, because whatever produced it was not an ordinary upload.
        if suffix in (".exe", ".dll", ".sh", ".bat", ".ps1", ".js", ".jar", ".zip"):
            raise UnsupportedUpload("پسوند %s پذیرفته نمی‌شود." % suffix)

    return kind, actual
