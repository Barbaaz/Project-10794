"""
Photos people upload (listing photos): checked, cleaned and kept.

process_photo() turns an upload into a safe JPEG: only real images (JPEG / PNG / WebP) are
accepted, turned the right way up, shrunk to MAX_SIZE px, and saved WITHOUT the hidden data
phones add (EXIF: GPS location, phone model…), plus a THUMB_SIZE thumbnail.

Where the files live is behind PhotoStorage: on this computer for now (LocalPhotoStorage,
instance/uploads, served by /media/…); a cloud storage can replace it when the site is hosted
without touching the rest.
"""
import io
import uuid
import warnings
from pathlib import Path

from PIL import Image, ImageOps

from app.config import INSTANCE_DIR

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIZE = 1600
THUMB_SIZE = 400
MAX_PIXELS = 50_000_000      # refuse "decompression bombs" (tiny files that expand to huge images)


class PhotoError(Exception):
    """An upload that isn't an acceptable photo; `code` is translated by the page."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def process_photo(data):
    """(photo JPEG bytes, thumbnail JPEG bytes) from an uploaded file's bytes, or PhotoError."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise PhotoError("photo_too_big")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            if image.format not in ALLOWED_FORMATS:
                raise PhotoError("photo_type")
            if image.width * image.height > MAX_PIXELS:
                raise PhotoError("photo_too_big")
            image.load()
    except PhotoError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise PhotoError("photo_type")

    image = ImageOps.exif_transpose(image).convert("RGB")   # the right way up, then EXIF is dropped
    return _jpeg(image, MAX_SIZE), _jpeg(image, THUMB_SIZE)


def _jpeg(image, size):
    copy = image.copy()
    copy.thumbnail((size, size))
    out = io.BytesIO()
    copy.save(out, "JPEG", quality=85, optimize=True)        # no exif= : saved without metadata
    return out.getvalue()


class LocalPhotoStorage:
    """Files under instance/uploads (never committed), served by the /media/<key> route."""

    def __init__(self, root=INSTANCE_DIR / "uploads"):
        self.root = Path(root)

    def save(self, folder, data):
        """Store the bytes as a new JPEG in `folder`; returns its key ("listings/12/ab12….jpg")."""
        key = f"{folder}/{uuid.uuid4().hex}.jpg"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def delete(self, key):
        (self.root / key).unlink(missing_ok=True)

    def url(self, key):
        return f"/media/{key}"


storage = LocalPhotoStorage()
