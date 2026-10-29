#!/usr/bin/env python3
"""Prepare Swift annotations with materialized image paths; check by default and write with --apply."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile

from dataset_utils import (DEFAULT_RELEASE, SPLITS, check_image, check_roots, load_entries,
                           paired_rows, relative_path, task_files, write_json)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE, help="Data release directory")
    parser.add_argument("--runtime-root", type=Path, required=True, help="Directory containing materialized images")
    parser.add_argument("--splits", nargs="+", choices=SPLITS, help="Process only the specified splits; default: all available splits")
    parser.add_argument("--apply", action="store_true", help="Write runtime/tasks_data; only check by default")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing runtime annotations")
    return parser.parse_args(argv)


def write_task(task_path: Path, destination: Path, runtime: Path, entries: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    split = task_path.stem
    meta_destination = destination.with_name(f"{split}_meta.jsonl")
    temporary_paths = []
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=f".{split}.", suffix=".jsonl",
                                         dir=destination.parent, delete=False) as samples_out:
            temporary_paths.append(Path(samples_out.name))
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=f".{split}_meta.", suffix=".jsonl",
                                             dir=destination.parent, delete=False) as metas_out:
                temporary_paths.append(Path(metas_out.name))
                for _, sample, meta in paired_rows(task_path):
                    entry = entries[meta["image_id"]]
                    sample["images"] = [str(runtime / relative_path(entry["output_relpath"], "output_relpath"))]
                    samples_out.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    metas_out.write(json.dumps(meta, ensure_ascii=False) + "\n")
        temporary_paths[0].replace(destination)
        temporary_paths[1].replace(meta_destination)
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)


def run(args) -> int:
    check_roots(args.release_root, args.runtime_root)
    entries = load_entries(args.release_root, args.splits)
    tasks = task_files(args.release_root, args.splits)
    runtime = args.runtime_root.resolve()
    counts, split_counts, errors = Counter(), Counter(), []
    verified = 0

    def inspect_image(entry):
        try:
            check_image(runtime / relative_path(entry["output_relpath"], "output_relpath"), entry)
            return None
        except Exception as exc:
            return {"image_id": entry["image_id"], "error": str(exc)}

    with ThreadPoolExecutor(max_workers=8) as pool:
        for error in pool.map(inspect_image, entries.values()):
            if error is None:
                verified += 1
            else:
                errors.append(error)
    for task_path in tasks:
        destination = runtime / task_path.relative_to(args.release_root)
        for target in (destination, destination.with_name(f"{task_path.stem}_meta.jsonl")):
            if target.exists() and not args.overwrite:
                errors.append({"error": f"Destination annotations already exist: {target}; use --overwrite to replace them"})
        task_name = str(task_path.parent.relative_to(args.release_root / "tasks_data"))
        sample_count = sum(1 for _ in paired_rows(task_path))
        counts[task_name] += sample_count
        split_counts[task_path.stem] += sample_count
    report = {"mode": "apply" if args.apply else "check", "tasks": len(counts),
              "selected_splits": [split for split in SPLITS if split in split_counts],
              "samples": sum(counts.values()), "per_task": dict(counts),
              "per_split": dict(split_counts),
              "verified_runtime_images": verified, "errors": errors, "written": False}
    if not errors and args.apply:
        for task_path in tasks:
            write_task(task_path, runtime / task_path.relative_to(args.release_root), runtime, entries)
        report["written"] = True
    write_json(runtime / "replace_paths_report.json", report)
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
