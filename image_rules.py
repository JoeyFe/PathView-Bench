"""Derive raw image locations and preparation parameters from public annotations."""
from __future__ import annotations

from pathlib import PurePosixPath
import re


_MACRO_METHODS = {
    "AGGC22": "pil_resize",
    "BACH": "bach_thumbnail",
    "BCNB": "pil_draft",
    "BRACS": "openslide_thumbnail",
    "CAMELYON16": "openslide_crop",
    "CAMELYON17": "openslide_crop",
    "DIGESTPATH2019": "pil_draft",
    "GTEX": "tiff_preview",
    "PANDAS": "openslide_crop",
    "TCGA_TUMOR": "tiff_preview",
    "TIGER": "vips_level",
    "TISSUENET": "openslide_crop",
}


def _source_relative(meta):
    path = PurePosixPath(meta["source_reference_path"])
    if path.parts[0].upper() != meta["source_dataset"].upper():
        raise ValueError("source_reference_path must begin with source_dataset")
    return PurePosixPath(*path.parts[1:])


def _raw_paths(dataset, task_level, source, output):
    """Map benchmark paths to the directory layout of each original data package."""
    name = output.name
    if dataset in {"CONIC", "PANNUKE", "BCNB", "DIGESTPATH2019", "GTEX",
                   "MIDOG2021", "NUCLS", "TCGA_TUMOR", "TISSUENET", "WSSS4LUAD"}:
        return [str(source)]
    if dataset == "AGGC22":
        subset, split = source.stem.split("_")[:2]
        return [f"AGGC2022_{split.lower()}/{subset}_{split}_image/{source.name}"]
    if dataset == "BACH":
        return [f"WSI/thumbnails/{source.stem}_thumb.png"]
    if dataset == "BCSS":
        return [f"CrowdsourcingDataset-Amgadetal2019/images/{name}"]
    if dataset == "BRACS":
        if task_level == "Slide_FOV":
            return [str(PurePosixPath("histoimage.na.icar.cnr.it/BRACS_WSI", *source.parts[1:]))]
        return [str(PurePosixPath("histoimage.na.icar.cnr.it/BRACS_RoI/latest_version", *output.parts[4:]))]
    if dataset == "CAMELYON16":
        if source.parts[0] == "testing":
            return [f"data/testing/images/{source.name}"]
        return [str(PurePosixPath("data", source))]
    if dataset == "CAMELYON17":
        return [f"data/images/{source.name}"]
    if dataset == "CONSEP":
        return [f"{source.parts[0].capitalize()}/Images/{source.name}"]
    if dataset == "GLAS":
        split = {"train": "train", "testA": "test_a", "testB": "test_b"}[name.split("_")[0]]
        return [f"{split}/img/{name}"]
    if dataset == "MONUSAC":
        parent = re.sub(r"[_-]\d+$", "", output.stem)
        split = output.parts[3]
        directory = "MoNuSAC_images_and_annotations" if split == "train" else "MoNuSAC_Testing_Data_and_Annotations"
        return [f"{directory}/{parent}/{name}"]
    if dataset == "OCELOT":
        kind = output.parts[3]
        return [f"ocelot2023_v1.0.1/images/{split}/{kind}/{name}" for split in ("train", "val", "test")]
    if dataset == "PANDAS":
        return [f"train_images/{source.name}"]
    if dataset == "SICAPV2":
        return [f"SICAPv2/images/{name}"]
    if dataset == "TIGER":
        if task_level == "Slide_FOV":
            return [f"wsibulk/images/{source.name}"]
        kind = output.parts[3].replace("_", "-")
        return [f"wsirois/roi-level-annotations/{kind}/images/{name}"]
    raise ValueError(f"Unsupported source dataset: {dataset}")


def _recipe(meta, output):
    dataset = meta["source_dataset"]
    if meta["task_level"] == "Slide_FOV":
        try:
            method = _MACRO_METHODS[dataset]
        except KeyError as exc:
            raise ValueError(f"Unsupported slide dataset: {dataset}") from exc
        recipe = {"operation": "macro", "method": method}
        recipe.update({key: meta[key] for key in ("base_size", "macro_size", "field_of_view", "level")})
        recipe["resample"] = "bilinear" if method == "tiff_preview" else "lanczos"
        if dataset == "TCGA_TUMOR":
            recipe["preview_min_long_edge"] = 2048
        return recipe
    if meta["task_level"] != "Region_FOV":
        raise ValueError(f"Unsupported task level: {meta['task_level']}")
    if dataset in {"CONIC", "PANNUKE"}:
        return {"operation": "npy", "index": int(output.stem), "output_size": meta["image_size"]}
    if dataset == "NUCLS":
        match = re.search(r"_left-(-?\d+)_top-(-?\d+)_bottom-(-?\d+)_right-(-?\d+)$", output.stem)
        if match is None:
            raise ValueError(f"NuCLS image filename must contain crop coordinates: {output.name}")
        left, top, bottom, right = map(int, match.groups())
        return {"operation": "crop", "method": "openslide", "level": 0,
                "field_of_view": [left, top, right, bottom],
                "output_size": meta["image_size"], "resample": "bicubic"}
    return {"operation": "copy"}


def infer_entry(sample: dict, meta: dict) -> dict:
    """Infer one internal image entry without adding processing fields to metadata."""
    images = sample.get("images")
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], str):
        raise ValueError("Each sample must contain one image path")
    output = PurePosixPath(images[0])
    expected = "macro_wsi" if meta["task_level"] == "Slide_FOV" else "local_fov"
    if len(output.parts) < 4 or output.parts[:2] != ("images", expected):
        raise ValueError(f"Image path must be under images/{expected}: {output}")
    source = _source_relative(meta)
    paths = _raw_paths(meta["source_dataset"], meta["task_level"], source, output)
    entry = {key: meta[key] for key in (
        "image_id", "source_dataset", "task_level", "source_reference_path", "image_size"
    )}
    entry.update(raw_relpath=paths[0], output_relpath=str(output), recipe=_recipe(meta, output))
    if len(paths) > 1:
        entry["raw_candidates"] = paths
    return entry
