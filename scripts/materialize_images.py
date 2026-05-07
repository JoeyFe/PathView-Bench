#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any


CODE_ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = CODE_ROOT.parent / "benchmark_release"
RAW_ROOTS = CODE_ROOT / "configs" / "raw_roots.example.json"
IMAGE_ROOT = Path("/path/to/img")
IMAGE_PLACEHOLDER_PREFIX = "/path/to/img/"
RAW_PLACEHOLDER_PREFIX = "/path/to/raw/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize benchmark image files from downloaded source datasets."
    )
    parser.add_argument("--release-root", type=Path, default=RELEASE_ROOT)
    parser.add_argument("--raw-roots", type=Path, default=RAW_ROOTS)
    parser.add_argument("--image-root", type=Path, default=IMAGE_ROOT)
    parser.add_argument("--datasets", nargs="*", default=None)
    parser.add_argument("--levels", nargs="*", choices=["Slide_FOV", "Region_FOV"], default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def jsonl_iter(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def output_path(image_placeholder: str, image_root: Path) -> Path:
    if not image_placeholder.startswith(IMAGE_PLACEHOLDER_PREFIX):
        raise ValueError(f"Unexpected image placeholder: {image_placeholder}")
    rel = image_placeholder.removeprefix(IMAGE_PLACEHOLDER_PREFIX)
    return image_root / rel


def raw_relative_path(raw_placeholder: str | None, dataset: str) -> Path | None:
    if not raw_placeholder or not raw_placeholder.startswith(RAW_PLACEHOLDER_PREFIX):
        return None
    rel = raw_placeholder.removeprefix(RAW_PLACEHOLDER_PREFIX)
    prefix = f"{dataset}/"
    if rel.startswith(prefix):
        return Path(rel.removeprefix(prefix))
    return Path(rel)


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".svs", ".bmp"}


@lru_cache(maxsize=64)
def indexed_files(root_text: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    root = Path(root_text)
    by_name: dict[str, list[str]] = {}
    by_stem: dict[str, list[str]] = {}
    if not root.is_dir():
        return by_name, by_stem
    for path in root.rglob("*"):
        if not path.is_file() or not is_image_file(path):
            continue
        by_name.setdefault(path.name, []).append(str(path))
        by_stem.setdefault(path.stem, []).append(str(path))
    return by_name, by_stem


def find_source_file(raw_root: Path, rel: Path | None, target_name: str) -> Path | None:
    candidates: list[Path] = []
    if rel is not None:
        candidates.extend([
            raw_root / rel,
            raw_root / rel.name,
        ])
    target = Path(target_name)
    candidates.append(raw_root / target.name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    by_name, by_stem = indexed_files(str(raw_root))
    if target.name in by_name and by_name[target.name]:
        return Path(sorted(by_name[target.name])[0])
    if target.stem in by_stem and by_stem[target.stem]:
        return Path(sorted(by_stem[target.stem])[0])
    if rel is not None:
        if rel.name in by_name and by_name[rel.name]:
            return Path(sorted(by_name[rel.name])[0])
        if rel.stem in by_stem and by_stem[rel.stem]:
            return Path(sorted(by_stem[rel.stem])[0])
    return None


def read_image(path: Path, level: int | None = None):
    from PIL import Image

    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff", ".svs"}:
        try:
            import tifffile

            with tifffile.TiffFile(path) as tif:
                series = tif.series[0]
                levels = list(getattr(series, "levels", []) or [series])
                use_level = min(max(level or 0, 0), len(levels) - 1)
                arr = levels[use_level].asarray()
            return Image.fromarray(arr).convert("RGB")
        except Exception:
            pass
    with Image.open(path) as image:
        return image.convert("RGB")


def save_image(image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        image.save(path, quality=95)
    elif suffix == ".bmp":
        image.save(path)
    else:
        image.save(path)


def scale_crop_box(crop_box: list[int], from_size: list[int], to_size: tuple[int, int]) -> tuple[int, int, int, int]:
    from_w, from_h = max(1, int(from_size[0])), max(1, int(from_size[1]))
    to_w, to_h = max(1, int(to_size[0])), max(1, int(to_size[1]))
    x1, y1, x2, y2 = [float(v) for v in crop_box]
    return (
        int(round(x1 * to_w / from_w)),
        int(round(y1 * to_h / from_h)),
        int(round(x2 * to_w / from_w)),
        int(round(y2 * to_h / from_h)),
    )


def parse_local_crop(image_relpath: str, image_size: list[int] | None) -> tuple[int, int, int, int] | None:
    name = Path(image_relpath).name
    match = re.search(r"_left-(\d+)_top-(\d+)_bottom-(\d+)_right-(\d+)", name)
    if match:
        left, top, bottom, right = [int(v) for v in match.groups()]
        return left, top, right, bottom
    match = re.search(r"_xmin(\d+)_ymin(\d+)", name)
    if match and image_size:
        x, y = [int(v) for v in match.groups()]
        return x, y, x + int(image_size[0]), y + int(image_size[1])
    match = re.search(r"_xini_(\d+)_yini_(\d+)", name)
    if match and image_size:
        x, y = [int(v) for v in match.groups()]
        return x, y, x + int(image_size[0]), y + int(image_size[1])
    return None


def materialize_macro(entry: dict, raw_root: Path, out_path: Path, dry_run: bool) -> str:
    asset = entry.get("macro_asset") or {}
    if asset.get("missing") or asset.get("asset_key") is None:
        raise RuntimeError(f"Missing macro asset for {entry['image_relpath']}")
    rel = raw_relative_path(entry.get("source_reference_path"), entry["source_dataset"])
    source = find_source_file(raw_root, rel, Path(entry["source_reference_relpath"] or entry["image_relpath"]).name)
    if source is None:
        raise FileNotFoundError(f"Could not locate raw source for {entry['image_relpath']} under {raw_root}")
    if dry_run:
        return f"macro {source} -> {out_path}"
    image = read_image(source, int(asset.get("level") or asset.get("preview_level") or 0))
    crop = scale_crop_box(asset["crop_box"], asset["base_thumb_size"], image.size)
    cropped = image.crop(crop)
    resized = cropped.resize(tuple(int(v) for v in asset["thumb_size"]))
    save_image(resized, out_path)
    return f"macro {source} -> {out_path}"


def materialize_local(entry: dict, raw_root: Path, out_path: Path, dry_run: bool) -> str:
    rel = Path(entry["image_relpath"])
    dataset_parts = rel.parts[3:] if len(rel.parts) > 3 else (rel.name,)
    direct_rel = Path(*dataset_parts)
    ref_rel = raw_relative_path(entry.get("source_reference_path"), entry["source_dataset"])
    source = find_source_file(raw_root, direct_rel, rel.name)
    if source is None:
        source = find_source_file(raw_root, ref_rel, rel.name)
    if source is None:
        raise FileNotFoundError(f"Could not locate local source for {entry['image_relpath']} under {raw_root}")
    crop = parse_local_crop(entry["image_relpath"], entry.get("image_size"))
    if dry_run:
        return f"local {source} -> {out_path}" + (f" crop={crop}" if crop else "")
    if crop is None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == out_path.suffix.lower():
            shutil.copy2(source, out_path)
        else:
            save_image(read_image(source), out_path)
        return f"local {source} -> {out_path}"
    image = read_image(source)
    cropped = image.crop(crop)
    image_size = entry.get("image_size")
    if image_size and list(cropped.size) != list(image_size):
        cropped = cropped.resize(tuple(int(v) for v in image_size))
    save_image(cropped, out_path)
    return f"local {source} -> {out_path}"


def main() -> None:
    args = parse_args()
    raw_roots = {key.upper(): Path(value) for key, value in load_json(args.raw_roots).items()}
    selected_datasets = {item.upper() for item in args.datasets} if args.datasets else None
    selected_levels = set(args.levels) if args.levels else None
    manifest_path = args.release_root / "metadata" / "image_manifest.jsonl"

    processed = 0
    skipped = 0
    failures: list[str] = []
    for entry in jsonl_iter(manifest_path):
        dataset = str(entry["source_dataset"]).upper()
        level = str(entry["task_level"])
        if selected_datasets and dataset not in selected_datasets:
            skipped += 1
            continue
        if selected_levels and level not in selected_levels:
            skipped += 1
            continue
        if args.limit is not None and processed >= args.limit:
            break
        raw_root = raw_roots.get(dataset)
        if raw_root is None:
            failures.append(f"{entry['image_relpath']}: missing raw root for {dataset}")
            continue
        out_path = output_path(entry["image_path"], args.image_root)
        try:
            if entry["generation_mode"] == "macro_asset":
                message = materialize_macro(entry, raw_root, out_path, args.dry_run)
            else:
                message = materialize_local(entry, raw_root, out_path, args.dry_run)
            processed += 1
            print(message)
        except Exception as exc:
            failures.append(f"{entry['image_relpath']}: {exc}")

    report = {
        "ok": not failures,
        "processed": processed,
        "skipped": skipped,
        "failure_count": len(failures),
        "failures": failures[:100],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
