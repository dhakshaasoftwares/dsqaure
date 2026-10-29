from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 1600


def compress_image(uploaded, max_side=MAX_SIDE, quality=80):
    """
    Phone photos are often 4–8 MB. Shrink them to a sensible size so a laptop
    disk does not fill up. Returns the original file if it is not an image.
    """
    if not uploaded:
        return uploaded
    try:
        uploaded.seek(0)
        img = Image.open(uploaded)
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError):
        uploaded.seek(0)
        return uploaded
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buffer = BytesIO()
    img.save(buffer, "JPEG", quality=quality, optimize=True)
    name = Path(getattr(uploaded, "name", "photo")).stem + ".jpg"
    return ContentFile(buffer.getvalue(), name=name)
