# ANZ BI Streamlit Portal

Streamlit BI portal for ANZ WeChat Pay New Intake and Activation Low-Activity analysis.

This repository is the clean Streamlit code home for the ANZ BI portal:

```text
https://github.com/KenX31/ANZBI.git
```

## Data Boundary

This repository is code-only. Do not commit raw exports, Excel workbooks, SQLite stores,
real processed data, `.env`, or Streamlit secrets.

Deployment data should live in the private data repository:

```text
KenX31/anzdata
projects/anz-bi-platform/
  manifest.json
  processed/
    new_intake/
    activation_low_activity/
    shared_dimensions/
```

## Local Run

On this workstation, the app automatically falls back to:

```text
D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform
```

Run:

```powershell
streamlit run app.py
```

To override the local data path:

```powershell
$env:DATA_BACKEND = "local"
$env:LOCAL_DATA_ROOT = "D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform"
streamlit run app.py
```

## Exports

Each BI page has two filtered exports:

- provider execution list: no `merchant_id`, `institution_id`, or other internal lookup IDs
- internal record list: includes MID / merchant IDs and institution IDs for follow-up lookup in internal systems

For Streamlit Cloud, configure secrets:

```toml
DATA_BACKEND = "github_private"
DATA_GITHUB_REPO = "KenX31/anzdata"
DATA_GITHUB_REF = "main"
DATA_PROJECT = "anz-bi-platform"
DATA_GITHUB_TOKEN = "..."
```

## Build Private Data Package

From this repo:

```powershell
python scripts\build_private_data_project.py `
  --output-root "D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform"
```

The script copies only reviewed processed outputs from the local analysis workspace and
writes a manifest with schema versions, row counts, source periods, and privacy levels.

## Streamlit Geo Staging Check

The new Streamlit-facing geo staging folder is:

```text
D:\Tencent\Data analysis\ANZ_Data_Warehouse\data\Geo_warehouse_streamlit_staging
```

Run the comparison without changing the deployed BI data:

```powershell
python scripts\compare_streamlit_geo_staging.py `
  --output-json tmp\geo_staging_comparison.json
```

Current full-data comparison result:

- New Intake: city coverage improves from `71.85%` to `72.63%`; suburb improves from `65.47%` to `69.45%`; geo_area drops from `63.33%` to `15.40%`; cluster drops from `25.27%` to `17.12%`.
- Activation Low-Activity: city coverage improves from `79.74%` to `92.70%`; suburb improves from `48.30%` to `92.60%`; geo_area drops from `52.58%` to `42.04%`; cluster drops from `50.08%` to `44.04%`.

Interpretation: the staging geo layer is better for city/suburb matching, especially Activation. It should not directly replace the current business-area/cluster enrichment yet, because the AU skinny table intentionally omits business-area and cluster fields. Keep business-area/cluster as a separate enrichment layer before switching production prepared data to the staging matcher.
