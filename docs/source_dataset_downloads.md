# Source Dataset Download And Placement Guide

The benchmark release files do not include images. Download each source dataset
from its official source when possible, place it under a local raw root, and
record that path in `configs/raw_roots.example.json`.

The image materialization script expects keys such as `PANDAS`, `TCGA_TUMOR`,
and `NUCLS`. The exact internal layout can follow the original dataset layout;
the script first tries release-relative paths, then falls back to filename and
stem search under the configured raw root.

| Dataset | Download / source | Suggested raw root key | Notes |
| --- | --- | --- | --- |
| AGGC22 | https://aggc22.grand-challenge.org/Data/ | `AGGC22` | Keep WSI images and per-class masks. |
| BACH | https://iciar2018-challenge.grand-challenge.org/Download/ | `BACH` | Keep annotated WSI images and XML region files. |
| BCNB | https://bupt-ai-cz.github.io/BCNB/ | `BCNB` | Keep WSI images and polygon annotation metadata. |
| BCSS | https://github.com/PathologyDataScience/BCSS | `BCSS` | Keep ROI images and TCGA slide references when available. |
| BRACS | https://www.bracs.icar.cnr.it/download/ | `BRACS` | Keep WSI and RoI folders. |
| CAMELYON16 | https://camelyon16.grand-challenge.org/Data/ | `CAMELYON16` | Keep training/test slides and XML annotations. |
| CAMELYON17 | https://camelyon17.grand-challenge.org/Data/ | `CAMELYON17` | Keep patient slide folders, XML annotations, and stage CSV. |
| CoNIC | https://github.com/TissueImageAnalytics/CoNIC | `CONIC` | Keep `images`, `labels_npy`, and metadata exports. |
| CoNSeP | https://github.com/vqdang/hover_net | `CONSEP` | Keep train/test images and MAT labels. |
| DigestPath2019 | https://digestpath2019.grand-challenge.org/Dataset/ | `DIGESTPATH2019` | Keep both tissue and signet-ring-cell subsets. |
| GlaS | https://warwick.ac.uk/fac/cross_fac/tia/data/glascontest/ | `GLAS` | Keep image and annotation folders. |
| GTEX | https://gtexportal.org/home/ | `GTEX` | Keep SVS slides and tissue metadata CSV. |
| MIDOG2021 | https://zenodo.org/records/4643381 | `MIDOG2021` | Keep images and mitosis annotation tables. |
| MoNuSAC | https://monusac-2020.grand-challenge.org/Data/ | `MONUSAC` | Keep image and XML annotation folders. |
| NuCLS | https://nucls.grand-challenge.org/ | `NUCLS` | Keep ROI images, annotations, and slide references. |
| OCELOT | https://zenodo.org/records/8417503 | `OCELOT` | Keep cell/tissue images, masks, and CSV annotations. |
| PANDAS | https://panda.grand-challenge.org/ | `PANDAS` | Keep train images, masks, and metadata CSV. |
| PanNuke | https://warwick.ac.uk/fac/cross_fac/tia/data/pannuke | `PANNUKE` | Keep fold-wise images and instance metadata. |
| SICAPv2 | https://zenodo.org/records/5320076 | `SICAPV2` | Keep patch images, masks, and partition spreadsheets. |
| TCGA_TUMOR | TCGA / GDC plus local tumor polygon archives | `TCGA_TUMOR` | Keep SVS slides and cohort polygon CSV archives. |
| TIGER | https://tiger.grand-challenge.org/Data/ | `TIGER` | Keep WSI, ROI images, tissue masks, and cell annotations. |
| TissueNet | https://www.data.gouv.fr/datasets/tissuenet-detect-lesions-in-uterine-cervix-specimens-open-data-set | `TISSUENET` | Keep WSI images and annotation CSV files. |
| WSSS4LUAD | https://wsss4luad.grand-challenge.org/Datasets/ | `WSSS4LUAD` | Keep patch images and semantic masks. |

Example workflow:

```bash
python scripts/materialize_images.py \
  --release-root ../benchmark_release \
  --raw-roots configs/raw_roots.example.json \
  --image-root /path/to/img \
  --dry-run --limit 10
```

After verifying the raw roots, remove `--dry-run` to generate images under
`/path/to/img/images/...`.
