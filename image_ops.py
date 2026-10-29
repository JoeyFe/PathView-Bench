"""Materialize images from raw data and transform macro-image and WSI level-0 coordinates."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image


Image.MAX_IMAGE_PIXELS = None


def _size(recipe):
    value = recipe.get("macro_size") or recipe.get("output_size") or recipe.get("image_size")
    return tuple(int(v) for v in value) if value is not None else None


def _box(recipe):
    value = recipe.get("field_of_view") or recipe.get("crop_box")
    return tuple(int(v) for v in value) if value is not None else None


def _resample(recipe, default="lanczos"):
    name = recipe.get("resample", default).lower()
    return {"lanczos": Image.Resampling.LANCZOS,
            "bilinear": Image.Resampling.BILINEAR,
            "bicubic": Image.Resampling.BICUBIC,
            "nearest": Image.Resampling.NEAREST}[name]


def _resize(image, recipe, default="lanczos"):
    size = _size(recipe)
    return image.resize(size, _resample(recipe, default)) if size and image.size != size else image


@lru_cache(maxsize=4)
def _npy_array(path):
    import numpy as np
    return np.load(path, mmap_mode="r", allow_pickle=False)


def _vips_image(source, arguments):
    """Read a selected image page or resize an image with vips."""
    with tempfile.TemporaryDirectory(prefix="pathview-vips-") as directory:
        target = Path(directory) / "image.png"
        command = ["vips", *arguments(str(source), str(target))]
        subprocess.run(command, check=True, capture_output=True, text=True)
        with Image.open(target) as handle:
            return handle.convert("RGB")


def _openslide_crop(source, recipe):
    import openslide
    level = int(recipe.get("level", 0))
    with openslide.OpenSlide(str(source)) as slide:
        dimensions = tuple(slide.level_dimensions[level])
        base = tuple(recipe.get("base_size") or dimensions)
        if base != dimensions:
            raise ValueError(f"base_size {base} does not match dimensions {dimensions} at level {level}")
        x1, y1, x2, y2 = _box(recipe) or (0, 0, *dimensions)
        downsample = float(slide.level_downsamples[level])
        origin = (int(round(x1 * downsample)), int(round(y1 * downsample)))
        image = slide.read_region(origin, level, (x2 - x1, y2 - y1)).convert("RGB")
    return _resize(image, recipe)


def _tiff_preview(source, recipe):
    import numpy as np
    import tifffile
    with tifffile.TiffFile(source) as handle:
        series = handle.series[0]
        levels = list(getattr(series, "levels", ()) or [series])
        if "preview_min_long_edge" in recipe:
            # Select the reading level independently of the coordinate reference level.
            target = int(recipe["preview_min_long_edge"])
            level = next((i for i in range(len(levels) - 1, -1, -1)
                          if max(levels[i].shape[:2]) >= target), len(levels) - 1)
        else:
            level = int(recipe["level"])
        array = levels[level].asarray()
    image = Image.fromarray(np.asarray(array)).convert("RGB")
    box = _box(recipe)
    base = recipe.get("base_size")
    if box and base:
        # Map coordinates from the reference dimensions to the selected image level.
        box = tuple(int(round(v * image.size[i % 2] / base[i % 2])) for i, v in enumerate(box))
        image = image.crop(box)
    return _resize(image, recipe, "bilinear")


def render_image(source_path, recipe):
    """Apply a recipe and return an independent RGB PIL image without writing a file."""
    source = Path(source_path)
    operation = recipe.get("operation", "macro")
    if operation == "npy":
        import numpy as np
        array = _npy_array(str(source))[int(recipe["index"])]
        return _resize(Image.fromarray(np.asarray(array).astype(np.uint8)).convert("RGB"), recipe)
    if operation == "crop":
        if recipe.get("method", "pil") == "openslide":
            return _openslide_crop(source, recipe)
        with Image.open(source) as handle:
            image = handle.convert("RGB")
        if _box(recipe):
            image = image.crop(_box(recipe))
        return _resize(image, recipe)
    if operation == "copy":
        with Image.open(source) as handle:
            return handle.convert("RGB")
    if operation != "macro":
        raise ValueError(f"Unsupported operation: {operation}")
    method = recipe["method"]
    if method == "openslide_crop":
        return _openslide_crop(source, recipe)
    if method == "openslide_thumbnail":
        import openslide
        with openslide.OpenSlide(str(source)) as slide:
            image = slide.get_thumbnail(_size(recipe)).convert("RGB")
        return _resize(image, recipe)
    if method == "pil_draft":
        with Image.open(source) as handle:
            handle.draft("RGB", _size(recipe))
            image = handle.convert("RGB")
        return _resize(image, recipe)
    if method == "pil_resize":
        with Image.open(source) as handle:
            image = handle.convert("RGB")
        return _resize(image, recipe)
    if method == "tiff_preview":
        return _tiff_preview(source, recipe)
    if method == "vips_level":
        level = int(recipe["level"])
        image = _vips_image(source, lambda src, dst: ["copy", f"{src}[page={level}]", dst])
        base = tuple(recipe.get("base_size") or image.size)
        if base != image.size:
            raise ValueError(f"base_size {base} does not match vips page {level} dimensions {image.size}")
        if _box(recipe):
            image = image.crop(_box(recipe))
        return _resize(image, recipe)
    if method == "bach_thumbnail":
        # Read the thumbnail included in the BACH data package.
        with Image.open(source) as handle:
            return _resize(handle.convert("RGB"), recipe)
    raise ValueError(f"Unsupported macro method: {method}")


def materialize(source_path, output_path, recipe):
    """Create a file with atomic replacement; copy does not decode the raw WSI."""
    source, output = Path(source_path), Path(output_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == output.resolve():
        raise ValueError("Source and output paths must differ")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{output.stem}.", suffix=output.suffix,
                                     dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        if recipe.get("operation") == "copy":
            shutil.copy2(source, temporary)
            size = None
        else:
            image = render_image(source, recipe)
            size = list(image.size)
            expected = _size(recipe)
            if expected and tuple(image.size) != expected:
                raise ValueError(f"Output dimensions {image.size} do not match expected dimensions {expected}")
            options = {"quality": int(recipe.get("jpeg_quality", 95))} if output.suffix.lower() in {".jpg", ".jpeg"} else {}
            image.save(temporary, **options)
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return {"operation": recipe.get("operation", "macro"), "method": recipe.get("method"),
            "output_size": size, "size_bytes": output.stat().st_size}


def macro_to_level0(coordinates, *, macro_size, field_of_view, base_size, level0_size):
    """Transform a pixel point [x,y] or box [x1,y1,x2,y2] using actual level dimensions."""
    if len(coordinates) not in (2, 4):
        raise ValueError("coordinates must be [x,y] or [x1,y1,x2,y2]")
    x1, y1, x2, y2 = map(float, field_of_view)
    offsets = (x1, y1)
    spans = (x2 - x1, y2 - y1)
    return [(offsets[i % 2] + float(v) * spans[i % 2] / macro_size[i % 2])
            * level0_size[i % 2] / base_size[i % 2] for i, v in enumerate(coordinates)]


def level0_to_macro(coordinates, *, macro_size, field_of_view, base_size, level0_size):
    """Invert macro_to_level0; input and output use floating-point pixel coordinates."""
    if len(coordinates) not in (2, 4):
        raise ValueError("coordinates must be [x,y] or [x1,y1,x2,y2]")
    x1, y1, x2, y2 = map(float, field_of_view)
    offsets = (x1, y1)
    spans = (x2 - x1, y2 - y1)
    return [(float(v) * base_size[i % 2] / level0_size[i % 2] - offsets[i % 2])
            * macro_size[i % 2] / spans[i % 2] for i, v in enumerate(coordinates)]
