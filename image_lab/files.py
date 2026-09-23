"""Image file I/O with Pillow. No Qt here, so this module is testable without a GUI."""

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps

from image_lab.model import IDENTITY, RGBA, TRANSPARENT, Edges, Transform, render

# Extensions accepted for drag-and-drop and shown in the open dialog.
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")

# Export formats by extension. Formats in NO_ALPHA_FORMATS get flattened onto white.
SAVE_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".bmp": "BMP"}
NO_ALPHA_FORMATS = {"JPEG", "BMP"}
JPEG_QUALITY = 95

# Default export folder: `out/` in the project folder (the install is editable).
# Created when first used.
OUT_DIR = Path(__file__).resolve().parent.parent / "out"


def is_image_path(path: str | Path) -> bool:
    """True if the path has one of the supported image extensions."""
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def load_image(path: str | Path | BinaryIO) -> Image.Image:
    """Load an image (file path or binary stream) as upright RGBA.

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


def next_free_path(folder: str | Path, stem: str, ext: str) -> Path:
    """First of `stem{ext}`, `stem_2{ext}`, `stem_3{ext}`, ... that doesn't exist yet."""
    folder = Path(folder)
    path = folder / f"{stem}{ext}"
    n = 2
    while path.exists():
        path = folder / f"{stem}_{n}{ext}"
        n += 1
    return path


def png_bytes(img: Image.Image) -> bytes:
    """Encode an image as PNG bytes (used for the clipboard, which keeps alpha this way)."""
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def ensure_extension(path: str | Path, default_ext: str) -> Path:
    """Append `default_ext` unless the path already ends in a supported save extension."""
    path = Path(path)
    if path.suffix.lower() in SAVE_FORMATS:
        return path
    return path.with_name(path.name + default_ext)


def save_image(
    img: Image.Image,
    edges: Edges,
    path: str | Path,
    fill: RGBA = TRANSPARENT,
    transform: Transform = IDENTITY,
):
    """Render `img` with its edits (see `model.render`) and save to `path`.

    The format comes from the extension.

    Raises ValueError for an unsupported extension, and OSError if writing fails.
    """
    path = Path(path)
    fmt = SAVE_FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise ValueError(f"Unsupported file type: {path.suffix or '(none)'}")
    out = render(img, edges, fill, transform)
    if fmt in NO_ALPHA_FORMATS:
        flat = Image.new("RGB", out.size, (255, 255, 255))
        flat.paste(out, mask=out.getchannel("A"))
        out = flat
    options = {"quality": JPEG_QUALITY} if fmt == "JPEG" else {}
    out.save(path, format=fmt, **options)
