"""Image file I/O with Pillow. No Qt here, so this module is testable without a GUI."""

from pathlib import Path

from PIL import Image, ImageOps

# Extensions accepted for drag-and-drop and shown in the open dialog.
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")


def is_image_path(path: str | Path) -> bool:
    """True if the path has one of the supported image extensions."""
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def load_image(path: str | Path) -> Image.Image:
    """Load an image as upright RGBA.

    Raises PIL.UnidentifiedImageError or OSError if the file can't be read;
    the caller decides how to report that.
    """
    with Image.open(path) as img:
        # Image.open is lazy; load now so the result doesn't depend on the open file.
        # For animated formats this reads the first frame, which is all we use.
        img.load()
        # Phone photos store rotation in EXIF instead of rotating the pixels.
        upright = ImageOps.exif_transpose(img)
        return upright.convert("RGBA")
