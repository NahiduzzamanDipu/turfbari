"""Uploaded turf pictures: validated with Pillow, re-encoded to WebP, EXIF (incl. GPS) stripped.

Re-encoding means we never serve the uploaded bytes themselves, so a file that only pretends to be
an image (or carries a payload after the image data) cannot reach visitors.
"""

import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000  # refuse decompression bombs before decoding
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}  # MPO = JPEG from many phone cameras
GALLERY_MAX_SIDE = 1920
THUMB_MAX_SIDE = 640
PROFILE_SIDE = 512


def _open(upload) -> Image.Image:
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"image": ["Pictures must be 10 MB or smaller."]})
    try:
        probe = Image.open(upload)
        if probe.format not in ALLOWED_FORMATS:
            raise ValidationError({"image": ["Upload a JPG, PNG or WebP picture."]})
        if probe.width * probe.height > MAX_PIXELS:
            raise ValidationError({"image": ["This picture is too large. Use one under 40 megapixels."]})
        probe.verify()  # structural check; the object is unusable afterwards
        upload.seek(0)
        image = Image.open(upload)
        image.load()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError({"image": ["This file is not a picture we can read."]}) from None
    image = ImageOps.exif_transpose(image)  # respect phone rotation, then drop EXIF
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "transparency" in image.info or image.mode in ("LA", "P") else "RGB")
    return image


def _webp(image: Image.Image, name: str, quality: int = 82) -> ContentFile:
    out = BytesIO()
    image.save(out, "WEBP", quality=quality, method=4)
    return ContentFile(out.getvalue(), name=name)


def _fit(image: Image.Image, side: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((side, side), Image.Resampling.LANCZOS)
    return copy


def process_gallery_photo(upload) -> tuple[ContentFile, ContentFile, int, int]:
    """Returns (large, thumbnail, width, height) of the large version."""
    image = _open(upload)
    large = _fit(image, GALLERY_MAX_SIDE)
    key = uuid.uuid4().hex
    return (
        _webp(large, f"{key}.webp"),
        _webp(_fit(image, THUMB_MAX_SIDE), f"{key}_thumb.webp", 78),
        *large.size,
    )


def process_profile_picture(upload) -> ContentFile:
    """Centre-cropped square, like a profile/logo picture."""
    image = _open(upload)
    square = ImageOps.fit(image, (PROFILE_SIDE, PROFILE_SIDE), Image.Resampling.LANCZOS)
    return _webp(square, f"{uuid.uuid4().hex}.webp", 85)
