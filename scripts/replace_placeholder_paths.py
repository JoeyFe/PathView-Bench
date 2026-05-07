#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path


TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".py", ".sh", ".csv"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace benchmark placeholder path prefixes in text files.")
    parser.add_argument("--root", type=Path, required=True, help="Directory to scan.")
    parser.add_argument("--image-root", help="Replacement for /path/to/img.")
    parser.add_argument("--raw-root", help="Replacement for /path/to/raw.")
    parser.add_argument("--apply", action="store_true", help="Rewrite files in place. Default is dry-run.")
    return parser.parse_args()


def iter_text_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def main() -> None:
    args = parse_args()
    replacements: list[tuple[str, str]] = []
    if args.image_root:
        replacements.append(("/path/to/img", args.image_root.rstrip("/")))
    if args.raw_root:
        replacements.append(("/path/to/raw", args.raw_root.rstrip("/")))
    if not replacements:
        raise SystemExit("Provide --image-root and/or --raw-root.")
    if not args.root.is_dir():
        raise SystemExit(f"Root directory does not exist: {args.root}")

    checked = 0
    changed = 0
    total = 0
    for path in iter_text_files(args.root):
        checked += 1
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = original
        file_count = 0
        for old, new in replacements:
            count = updated.count(old)
            if count:
                updated = updated.replace(old, new)
                file_count += count
        if file_count == 0:
            continue
        changed += 1
        total += file_count
        print(f"{path}: replacements={file_count}")
        if args.apply:
            path.write_text(updated, encoding="utf-8")

    print(f"apply={args.apply}")
    print(f"checked_files={checked}")
    print(f"changed_files={changed}")
    print(f"total_replacements={total}")


if __name__ == "__main__":
    main()
