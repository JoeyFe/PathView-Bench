#!/usr/bin/env python3
"""Materialize images from official raw data; check by default and write with --apply."""
from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import sys
import tempfile

from dataset_utils import (DEFAULT_RELEASE, SPLITS, check_image, check_roots, load_entries,
                           read_roots, read_tcga_index, relative_path, resolve_source, task_files, write_json)


@lru_cache(maxsize=4)
def load_npy(path: str):
    import numpy as np

    return np.load(path, mmap_mode="r", allow_pickle=False)


def preflight_source(source: Path, recipe: dict) -> None:
    if recipe["operation"] == "npy":
        array = load_npy(str(source))
        index = recipe.get("index")
        if not isinstance(index, int) or not 0 <= index < len(array):
            raise ValueError(f"Invalid NPY index: {source}, index={index}, shape={array.shape}")
        if array[index].ndim != 3:
            raise ValueError(f"Each NPY image must be a three-dimensional array: {source}, shape={array[index].shape}")


def create_image(source: Path, output: Path, entry: dict) -> None:
    from image_ops import materialize

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{output.stem}.", suffix=output.suffix,
                                     dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        materialize(source, temporary, entry["recipe"])
        check_image(temporary, entry)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE, help="Data release directory")
    parser.add_argument("--raw-roots", type=Path, required=True, help="JSON configuration of official raw data directories")
    parser.add_argument("--runtime-root", type=Path, required=True, help="Output directory for materialized images and inference annotations")
    parser.add_argument("--tcga-index", type=Path, help="Optional index mapping complete slide filename stems to raw file paths")
    parser.add_argument("--splits", nargs="+", choices=SPLITS, help="Process only the specified splits; default: all available splits")
    parser.add_argument("--datasets", nargs="+", help="Process only the specified datasets")
    parser.add_argument("--levels", nargs="+", choices=["Slide_FOV", "Region_FOV"], help="Process only the specified field-of-view levels")
    parser.add_argument("--limit", type=int, help="Maximum number of unique images to process")
    parser.add_argument("--apply", action="store_true", help="Write images; only check by default")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate existing images")
    return parser.parse_args(argv)


def run(args) -> int:
    check_roots(args.release_root, args.runtime_root)
    if args.limit is not None and args.limit <= 0:
        raise ValueError("limit must be greater than 0")
    roots, slides = read_roots(args.raw_roots), read_tcga_index(args.tcga_index)
    all_entries = load_entries(args.release_root, args.splits)
    selected_splits = [split for split in SPLITS
                       if any(path.stem == split for path in task_files(args.release_root, args.splits))]
    entries = [entry for entry in all_entries.values()
               if (not args.datasets or entry["source_dataset"] in args.datasets)
               and (not args.levels or entry["task_level"] in args.levels)]
    total_matching = len(entries)
    if args.limit is not None:
        entries = entries[:args.limit]
    if not entries:
        raise ValueError("No images match the filters")
    counts, source_bytes, errors = Counter(), {}, []
    for number, entry in enumerate(entries, 1):
        try:
            source = resolve_source(entry, roots, slides)
            preflight_source(source, entry["recipe"])
            source_bytes[str(source)] = source.stat().st_size
            output = args.runtime_root / relative_path(entry["output_relpath"], "output_relpath")
            if output.exists() and not args.overwrite:
                check_image(output, entry)
                status = "existing"
            elif args.apply:
                create_image(source, output, entry)
                status = "written"
            else:
                status = "planned"
            counts[status] += 1
        except Exception as exc:
            counts["error"] += 1
            errors.append({"image_id": entry["image_id"], "error": str(exc)})
        if number % 500 == 0:
            print(f"Processed {number}/{len(entries)} images", flush=True)
    report = {"mode": "apply" if args.apply else "check", "selected_splits": selected_splits,
              "selected_images": len(entries),
              "total_matching_images": total_matching, "total_release_images": len(all_entries),
              "counts": dict(counts), "unique_source_files": len(source_bytes),
              "unique_source_bytes": sum(source_bytes.values()), "errors": errors}
    write_json(args.runtime_root / "materialize_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(errors))


def main(argv=None) -> int:
    try:
        return run(parse_args(argv))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
