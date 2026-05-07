# Benchmark Release Utilities

This directory contains the placeholder path rewrite and image materialization
utilities for the annotation package. The annotation package contains VQA JSONL
files but no image files.

## Materialize Images

Edit `configs/raw_roots.example.json` so each dataset key points to your local
downloaded source dataset directory. Then run:

```bash
python scripts/materialize_images.py \
  --release-root ../benchmark_release \
  --raw-roots configs/raw_roots.example.json \
  --image-root /path/to/img \
  --dry-run --limit 10
```

Remove `--dry-run` after the source roots are verified.

## Replace Placeholders

```bash
python scripts/replace_placeholder_paths.py \
  --root ../benchmark_release \
  --image-root /actual/benchmark/images \
  --raw-root /actual/benchmark/raw \
  --apply
```
