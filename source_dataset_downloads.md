# Source Dataset Download and Placement Guide

The Pathview-bench annotation package does not include image files. Obtain each
source dataset from the source listed below, extract the required files, and set
its local root in `raw_roots.json`. Start with `raw_roots.example.json`.

The configuration keys must match the annotations' `source_dataset` values.
`image_rules.py` maps the sample paths and metadata to the original dataset
directories. Keep the directory names and filename capitalization expected by
those rules. The benchmark's available train, val, or test splits are independent
of the source dataset's own directory names.

| Dataset | Download / source | Raw root key | Required image files and layout under the configured root |
| --- | --- | --- | --- |
| AGGC22 | https://aggc22.grand-challenge.org/Data/ | `AGGC22` | `AGGC2022_train/Subset*_Train_image/*.tiff` and `AGGC2022_test/Subset*_Test_image/*.tiff`. |
| BACH | https://iciar2018-challenge.grand-challenge.org/Download/ | `BACH` | Keep `WSI/` and the source package's `WSI/thumbnails/*_thumb.png`. |
| BCNB | https://bupt-ai-cz.github.io/BCNB/ | `BCNB` | `WSIs/*.jpg`. |
| BCSS | https://github.com/PathologyDataScience/BCSS | `BCSS` | `CrowdsourcingDataset-Amgadetal2019/images/*.png`; these are the original ROI images. |
| BRACS | https://www.bracs.icar.cnr.it/download/ | `BRACS` | `histoimage.na.icar.cnr.it/BRACS_WSI/` and `histoimage.na.icar.cnr.it/BRACS_RoI/latest_version/`, including their split and class subdirectories. |
| CAMELYON16 | https://camelyon16.grand-challenge.org/Data/ | `CAMELYON16` | `data/training/normal/*.tif`, `data/training/tumor/*.tif`, and `data/testing/images/*.tif`. |
| CAMELYON17 | https://camelyon17.grand-challenge.org/Data/ | `CAMELYON17` | `data/images/*.tif`. |
| CoNIC | https://github.com/TissueImageAnalytics/CoNIC | `CONIC` | Original `data/images.npy`; individual PNG files are extracted by the tool. |
| CoNSeP | https://github.com/vqdang/hover_net | `CONSEP` | `Train/Images/*.png` and `Test/Images/*.png`. |
| DigestPath2019 | https://digestpath2019.grand-challenge.org/Dataset/ | `DIGESTPATH2019` | `Colonoscopy_tissue_segment_dataset/tissue-train-pos-v1/`, `Colonoscopy_tissue_segment_dataset/tissue-train-neg/`, and `Signet_ring_cell_dataset/sig-train-pos/`. |
| GlaS | https://warwick.ac.uk/fac/cross_fac/tia/data/glascontest/ | `GLAS` | `train/img/*.bmp`, `test_a/img/*.bmp`, and `test_b/img/*.bmp`. |
| GTEX | https://gtexportal.org/home/ | `GTEX` | Original `GTEX-*.svs` slides. |
| MIDOG2021 | https://zenodo.org/records/4643381 | `MIDOG2021` | Original numbered `*.tiff` images. |
| MoNuSAC | https://monusac-2020.grand-challenge.org/Data/ | `MONUSAC` | Original region images in `MoNuSAC_images_and_annotations/<slide>/` and `MoNuSAC_Testing_Data_and_Annotations/<slide>/`. |
| NuCLS | https://nucls.grand-challenge.org/ | `NUCLS` | Original TCGA WSI files referenced by the annotations. Configure the TCGA download root; regions are cropped from the slides by the tool. |
| OCELOT | https://zenodo.org/records/8417503 | `OCELOT` | `ocelot2023_v1.0.1/images/{train,val,test}/{cell,tissue}/`; retain the cell and tissue subdirectories. |
| PANDAS | https://panda.grand-challenge.org/ | `PANDAS` | Original `train_images/*.tiff` slides. |
| PanNuke | https://warwick.ac.uk/fac/cross_fac/tia/data/pannuke | `PANNUKE` | Original `Fold n/images/foldn/images.npy` for folds 1, 2, and 3. Individual PNG files are extracted by the tool. |
| SICAPv2 | https://data.mendeley.com/datasets/9xxm58dvs3/1 | `SICAPV2` | Original patch images under `SICAPv2/images/`. |
| TCGA_TUMOR | https://portal.gdc.cancer.gov/ | `TCGA_TUMOR` | Original TCGA slide files. The tool searches the configured root by complete slide filenames, including GDC subdirectories. |
| TIGER | https://tiger.grand-challenge.org/Data/ | `TIGER` | `wsibulk/images/`, `wsirois/roi-level-annotations/tissue-cells/images/`, and `wsirois/roi-level-annotations/tissue-bcss/images/`. |
| TissueNet | https://www.data.gouv.fr/datasets/tissuenet-detect-lesions-in-uterine-cervix-specimens-open-data-set | `TISSUENET` | Original slide files under `images/`. |
| WSSS4LUAD | https://wsss4luad.grand-challenge.org/Datasets/ | `WSSS4LUAD` | Original patch images and source subdirectories, including `1.training/`, `2.validation/`, and `3.testing/`. |

The layout column describes the paths used by the tools. If an archive extracts
with a different outer directory, select the root that gives the listed paths,
or arrange those outer directories accordingly. Keep the original arrays, WSI
files, ROI images, and patch images; prepared benchmark images are not required.
The supplied task annotations provide the labels needed by the image preparation
workflow. Follow each source dataset's access and usage terms when obtaining it.

`NUCLS` and `TCGA_TUMOR` may share one TCGA root. An optional
`--tcga-index /path/to/tcga_slide_index.json` can map complete slide filename stems
to their actual file paths, as described in the main README.

## Prepare Images

Run from the code directory after installing the dependencies:

```bash
cp raw_roots.example.json raw_roots.json
```

Edit `raw_roots.json`, then check the source paths without generating images:

```bash
python materialize_images.py \
  --release-root /path/to/Pathview-bench \
  --raw-roots raw_roots.json \
  --runtime-root /path/to/Pathview-bench-runtime
```

Add `--apply` to generate images. By default, all available splits are processed;
use `--splits train val` or `--splits test` to select them. Use `--limit 10` for an
initial check of a small number of images.

The generated images are written under `images/local_fov/` and `images/macro_wsi/`
inside the runtime root. Continue with **Replace Placeholders** in the
[main README](README.md) to generate the runtime annotation files.
