# Pathview-Bench Tools

Prepare task input images for `Pathview-Bench` from official original datasets and generate runtime annotations for Swift. The tools discover available `train`, `val`, and `test` splits from the input annotations and preserve their names and task structure.

The input layout is `tasks_data/<task>/{train,val,test}.jsonl`, with a matching `{train,val,test}_meta.jsonl` for each available split. Only available splits are required. By default, both tools process all available splits; add `--splits train val` or `--splits test` to select specific splits.

## Installation

Python 3.10 or later, the system OpenSlide library, and the libvips command-line tools are required. On Ubuntu or Debian:

```bash
sudo apt-get install libopenslide0 libvips-tools
python -m pip install -r requirements.txt
```

For Swift inference, also install `ms-swift` and the dependencies required by the selected model.

## Configure Original Datasets

See the [Source Dataset Download and Placement Guide](source_dataset_downloads.md)
for dataset sources, configuration keys, and the required directory layouts.

Run from this code directory:

```bash
cp raw_roots.example.json raw_roots.json
```

Edit `raw_roots.json` to set the local original data root for each of the 23 datasets. For example:

```json
{
  "CONIC": "/data/CoNIC",
  "PANNUKE": "/data/PanNuke",
  "PANDAS": "/data/PANDA"
}
```

Only three entries are shown above; see `raw_roots.example.json` for the complete configuration. The scripts use `source_dataset`, `source_reference_path`, and the prepared image paths in `<split>.jsonl` to locate source files within each official dataset's directory structure. For example, a `CONIC` root of `/data/CoNIC` resolves the source array to `/data/CoNIC/data/images.npy`. Native ROI images are located by their prepared filenames within the corresponding dataset's original image directories.

Use the original array and image files: CoNIC uses `images.npy`, and PanNuke uses the `images.npy` file for each fold. WSI datasets use original slide files; region datasets use their original ROI or patch images. PNG regions and WSI thumbnails do not need to be generated in advance.

## Materialize Images

Prepare task input images using the sample paths and metadata. Dataset-specific reading and resizing defaults are defined in the code:

- Native ROI / patch images: copy the corresponding region image.
- CoNIC / PanNuke: extract the RGB image at the index encoded in the prepared image filename. PanNuke's fold is identified by the image path.
- NuCLS: recover the crop coordinates from the prepared image filename, read that region from the original WSI, and resize it to `image_size`.
- Slide-FOV: generate a macro image using `base_size`, `macro_size`, `level`, and `field_of_view`.

```bash
python materialize_images.py \
  --release-root /path/to/Pathview-Bench \
  --raw-roots raw_roots.json \
  --runtime-root /path/to/Pathview-Bench-runtime \
  --apply
```

Output images are written to `runtime/images/local_fov/` and `runtime/images/macro_wsi/`. Omit `--apply` to check the source files and image specifications. Use `--datasets CONIC PANNUKE`, `--levels Slide_FOV`, or `--limit 10` to select a subset of images. Existing images are reused on subsequent runs; add `--overwrite` to regenerate them.

`NUCLS` and `TCGA_TUMOR` can share the same TCGA download root. The scripts search that root by the full slide filename. To specify slide locations directly, add `--tcga-index /path/to/tcga_slide_index.json`. The index's `slides` object maps each full slide filename stem to the absolute path of the corresponding file:

```json
{
  "slides": {
    "TCGA-EXAMPLE-01Z-00-DX1.UUID": "/data/TCGA/TCGA-EXAMPLE-01Z-00-DX1.UUID.svs"
  }
}
```

## Replace Placeholders

After preparing the images, resolve the relative output paths in each selected `<split>.jsonl` against the runtime root:

```bash
python replace_placeholder_paths.py \
  --release-root /path/to/Pathview-Bench \
  --runtime-root /path/to/Pathview-Bench-runtime \
  --apply
```

The release's `images` entries are relative paths such as `images/local_fov/...` or `images/macro_wsi/...`. The outputs are `runtime/tasks_data/<task>/<split>.jsonl` and `<split>_meta.jsonl`, with `images` converted to absolute paths under the runtime root. `source_reference_path` continues to identify the original source; distinct regions from the same WSI retain separate image identifiers and output paths. Questions, reference answers, and `objects` are preserved. Omit `--apply` to check only the inputs; add `--overwrite` to regenerate existing runtime annotations.

The resulting directory structure is:

```text
Pathview-Bench-runtime/
├── images/
│   ├── local_fov/
│   └── macro_wsi/
└── tasks_data/
    └── <task>/
        ├── {train,val,test}.jsonl
        └── {train,val,test}_meta.jsonl
```

Only the selected available splits are written to the runtime directory. For example, `--splits train val` processes train and val, while `--splits test` processes test.

## Swift Inference Example

Run the Slide-FOV lesion grounding task through the `swift infer` workflow:

```bash
PATHVIEW_ROOT=/path/to/Pathview-Bench-runtime
PATHVIEW_SPLIT=test
CUDA_VISIBLE_DEVICES=0 swift infer \
  --model Qwen/Qwen3-VL-8B-Instruct \
  --val_dataset "${PATHVIEW_ROOT}/tasks_data/slide_fov_lesion_grounding/${SPLIT}.jsonl" \
  --result_path outputs/qwen3vl_lesion_grounding.jsonl
```

Each sample provides `messages`, image input, the answer format, and the `objects` required for grounding tasks. The `<bbox>` placeholders in grounding reference answers correspond to `objects.bbox` in order. `bbox_type: norm1` indicates coordinates normalized to `[0, 1]` relative to the task input image.

To map coordinates back to the original WSI, use `base_size`, `macro_size`, `field_of_view`, and `level0_size` from the Slide-FOV metadata. Coordinate conversion functions are provided in `image_ops.py`.
