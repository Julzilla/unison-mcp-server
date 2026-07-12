"""Utility helpers for validating image inputs."""

import base64
import binascii
import os
import stat
from collections.abc import Iterable

from utils.file_types import IMAGES, get_image_mime_type

DEFAULT_MAX_IMAGE_SIZE_MB = 20.0

__all__ = ["DEFAULT_MAX_IMAGE_SIZE_MB", "validate_image"]


def _valid_mime_types() -> Iterable[str]:
    """Return the MIME types permitted by the IMAGES whitelist."""
    return (get_image_mime_type(ext) for ext in IMAGES)


def validate_image(image_path: str, max_size_mb: float | None = None) -> tuple[bytes, str]:
    """Validate a user-supplied image path or data URL.

    Args:
        image_path: Either a filesystem path or a data URL.
        max_size_mb: Optional size limit (defaults to ``DEFAULT_MAX_IMAGE_SIZE_MB``).

    Returns:
        A tuple ``(image_bytes, mime_type)`` ready for upstream providers.

    Raises:
        ValueError: When the image is missing, malformed, or exceeds limits.
    """
    if max_size_mb is None:
        max_size_mb = DEFAULT_MAX_IMAGE_SIZE_MB

    if image_path.startswith("data:"):
        return _validate_data_url(image_path, max_size_mb)

    return _validate_file_path(image_path, max_size_mb)


def _validate_data_url(image_data_url: str, max_size_mb: float) -> tuple[bytes, str]:
    """Validate a data URL and return image bytes plus MIME type."""
    try:
        header, data = image_data_url.split(",", 1)
        mime_type = header.split(";")[0].split(":")[1]
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Invalid data URL format: {exc}")

    valid_mime_types = list(_valid_mime_types())
    if mime_type not in valid_mime_types:
        raise ValueError(
            "Unsupported image type: {mime}. Supported types: {supported}".format(
                mime=mime_type, supported=", ".join(valid_mime_types)
            )
        )

    try:
        image_bytes = base64.b64decode(data)
    except binascii.Error as exc:
        raise ValueError(f"Invalid base64 data: {exc}")

    _validate_size(image_bytes, max_size_mb)
    return image_bytes, mime_type


def _validate_file_path(file_path: str, max_size_mb: float) -> tuple[bytes, str]:
    """Validate an image loaded from the filesystem.

    Ordering is security-sensitive: we ``stat`` (never an unbounded ``read``)
    first, reject anything that is not a regular file, and check the size up
    front. Only then do we read, and the read is hard-capped. This prevents a
    crafted path (``/dev/zero``, a FIFO, a ``/proc`` pseudo-file, or a symlink
    to any of them) from exhausting memory or blocking the request forever, and
    prevents a genuinely huge image from being fully buffered before the size
    limit is consulted.
    """
    # stat() first (follows symlinks to the real target). FileNotFoundError is
    # surfaced before the extension check so a non-image path that does not
    # exist still reports "Image file not found".
    try:
        st = os.stat(file_path)
    except FileNotFoundError:
        raise ValueError(f"Image file not found: {file_path}")
    except OSError as exc:
        raise ValueError(f"Failed to read image file: {exc}")

    if not stat.S_ISREG(st.st_mode):
        raise ValueError(f"Image path is not a regular file: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in IMAGES:
        raise ValueError(
            "Unsupported image format: {ext}. Supported formats: {supported}".format(
                ext=ext, supported=", ".join(sorted(IMAGES))
            )
        )

    max_bytes = int(max_size_mb * 1024 * 1024)
    if st.st_size > max_bytes:
        size_mb = st.st_size / (1024 * 1024)
        raise ValueError(f"Image too large: {size_mb:.1f}MB (max: {max_size_mb}MB)")

    # Hard-capped read: at most max_bytes + 1 so a file that grows between stat
    # and read (or a pseudo-file that under-reports st_size) still cannot
    # exhaust memory. The trailing byte lets _validate_size flag an overflow.
    try:
        with open(file_path, "rb") as handle:
            image_bytes = handle.read(max_bytes + 1)
    except FileNotFoundError:
        raise ValueError(f"Image file not found: {file_path}")
    except OSError as exc:
        raise ValueError(f"Failed to read image file: {exc}")

    mime_type = get_image_mime_type(ext)
    _validate_size(image_bytes, max_size_mb)
    return image_bytes, mime_type


def _validate_size(image_bytes: bytes, max_size_mb: float) -> None:
    """Ensure the image does not exceed the configured size limit."""
    size_mb = len(image_bytes) / (1024 * 1024)
    if size_mb > max_size_mb:
        raise ValueError(f"Image too large: {size_mb:.1f}MB (max: {max_size_mb}MB)")
