"""Load annotations, resolve paths, and check image dimensions."""
from __future__ import annotations

from functools import lru_cache
from itertools import zip_longest
import json
from pathlib import Path, PurePosixPath

from image_rules import infer_entry


DEFAULT_RELEASE = Path(__file__).resolve().parent.parent / "Pathview-bench"
SPLITS = ("train", "val", "test")


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON: {path}:{number}: {exc}") from exc


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relative_path(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{label} must be a nonempty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise ValueError(f"{label} must be a relative file path: {value}")
    return Path(*path.parts)


def check_roots(release: Path, runtime: Path) -> None:
    release, runtime = release.resolve(), runtime.resolve()
    if runtime == release or runtime.is_relative_to(release):
        raise ValueError("runtime-root must be outside the release directory")


def task_files(release: Path, splits: list[str] | None = None) -> list[Path]:
    selected = set(SPLITS if splits is None else splits)
    if not selected.issubset(SPLITS):
        raise ValueError(f"Unsupported splits: {sorted(selected.difference(SPLITS))}")
    paths = sorted(path for split in selected
                   for path in (release / "tasks_data").rglob(f"{split}.jsonl"))
    if not paths:
        raise ValueError(f"No annotations found for the selected splits: {release / 'tasks_data'}")
    return paths


def paired_rows(task_path: Path):
    split = task_path.stem
    meta_path = task_path.with_name(f"{split}_meta.jsonl")
    for number, (sample, meta) in enumerate(
        zip_longest(read_jsonl(task_path), read_jsonl(meta_path)), 1
    ):
        if sample is None or meta is None:
            raise ValueError(f"Annotation and metadata row counts differ: {task_path}, row {number}")
        if meta.get("split", split) != split:
            raise ValueError(f"{meta_path}, row {number}: split must be {split}")
        yield number, sample, meta


def load_entries(release: Path, splits: list[str] | None = None) -> dict[str, dict]:
    """Deduplicate input images and derive preparation parameters from annotations."""
    entries, outputs = {}, {}
    for task_path in task_files(release, splits):
        for number, sample, meta in paired_rows(task_path):
            try:
                entry = infer_entry(sample, meta)
                image_id = entry["image_id"]
                if not isinstance(image_id, str) or not image_id:
                    raise ValueError("image_id must be a nonempty string")
                relative_path(entry["raw_relpath"], "raw_relpath")
                relative_path(entry["source_reference_path"], "source_reference_path")
                output = relative_path(entry["output_relpath"], "output_relpath")
                if len(output.parts) < 3 or output.parts[:2] not in {
                    ("images", "macro_wsi"), ("images", "local_fov")
                }:
                    raise ValueError("output_relpath must be under images/macro_wsi or images/local_fov")
                if entry["recipe"].get("operation") not in {"copy", "npy", "macro", "crop"}:
                    raise ValueError(f"Unsupported image operation: {entry['recipe'].get('operation')}")
                size = entry["image_size"]
                if len(size) != 2 or any(not isinstance(v, int) or v <= 0 for v in size):
                    raise ValueError("image_size must be a [width, height] array of positive integers")
                if image_id in entries and entries[image_id] != entry:
                    raise ValueError(f"Inconsistent source or processing parameters for image_id: {image_id}")
                if str(output) in outputs and outputs[str(output)] != image_id:
                    raise ValueError(f"Different image_id values cannot share an output path: {output}")
                entries[image_id], outputs[str(output)] = entry, image_id
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{task_path}, row {number}: {exc}") from exc
    if not entries:
        raise ValueError("No images found in the selected annotations")
    return entries


def read_roots(path: Path) -> dict[str, Path]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(not isinstance(value, str) for value in data.values()):
        raise ValueError("raw-roots must be a JSON object mapping dataset names to raw data directories")
    roots = {}
    for dataset, value in data.items():
        root = Path(value).expanduser()
        roots[dataset] = root if root.is_absolute() else path.resolve().parent / root
    return roots


def read_tcga_index(path: Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    slides = data.get("slides", data)
    if not isinstance(slides, dict):
        raise ValueError("The TCGA index must map complete slide filename stems to file paths")
    result = {}
    for stem, value in slides.items():
        key = stem.casefold()
        source = Path(value).expanduser()
        if not source.is_absolute():
            source = path.resolve().parent / source
        if key in result and result[key] != source:
            raise ValueError(f"Duplicate complete slide filename stem in TCGA index: {stem}")
        result[key] = source
    return result


@lru_cache(maxsize=64)
def _tcga_files(root: Path) -> dict[str, dict[Path, Path]]:
    """Index complete filenames once per raw data root, including GDC subdirectories."""
    names = {}
    for path in root.rglob("*"):
        if path.suffix.lower() in {".svs", ".ndpi", ".mrxs", ".tif", ".tiff"} and path.is_file():
            names.setdefault(path.name.casefold(), {})[path.resolve()] = path
    return names


def resolve_source(entry: dict, roots: dict[str, Path], slides: dict[str, Path]) -> Path:
    dataset = entry["source_dataset"]
    rel = relative_path(entry["raw_relpath"], "raw_relpath")
    root = roots.get(dataset)
    if root is not None:
        matches = {}
        for value in entry.get("raw_candidates", [str(rel)]):
            candidate = root / relative_path(value, "raw candidate")
            if candidate.is_file():
                matches[candidate.resolve()] = candidate
        if len(matches) > 1:
            raise ValueError(f"Multiple raw files match the input image: {entry['output_relpath']}; {list(matches.values())}")
        if matches:
            return next(iter(matches.values()))
    if dataset.upper().startswith("TCGA") or dataset.upper() == "NUCLS" or rel.stem.upper().startswith("TCGA-"):
        indexed = slides.get(rel.stem.casefold())
        if indexed is not None and indexed.is_file():
            return indexed
        if root is not None and root.is_dir():
            matches = _tcga_files(root.resolve()).get(rel.name.casefold(), {})
            if len(matches) > 1:
                raise ValueError(f"Multiple raw files match the complete slide filename: {rel.name}; {list(matches.values())}")
            if matches:
                return next(iter(matches.values()))
    if root is None:
        raise FileNotFoundError(f"Dataset directory missing from raw-roots: {dataset}")
    raise FileNotFoundError(f"Raw file not found under {root}: {entry.get('raw_candidates', [str(rel)])}")


@lru_cache(maxsize=65536)
def _image_size(path: str, size_bytes: int, mtime_ns: int) -> tuple[int, int]:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as image:
        return image.size


def image_size(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return _image_size(str(path), stat.st_size, stat.st_mtime_ns)


def check_image(path: Path, entry: dict) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    actual = image_size(path)
    if list(actual) != entry["image_size"]:
        raise ValueError(f"Image dimensions do not match: {path}; got {actual}, expected {entry['image_size']}")
