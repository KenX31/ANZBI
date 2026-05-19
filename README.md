# ANZ BI Streamlit Portal

Streamlit BI portal for ANZ WeChat Pay New Intake, Activation Low-Activity, Rate Coupon Activity, and Silent Merchants analysis.

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
    rate_coupon_activity/
    silent_merchants/
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

## Authentication

The BI portal supports two authentication modes:

- `local`: email + password accounts stored in Streamlit secrets as password hashes
- `ldap`: optional LDAP / Active Directory login through
  [`streamlit-ldap-authenticator`](https://github.com/NathanChen198/streamlit-ldap-authenticator)

For ANZ team access without connecting to a company directory server, use `local`.

Authentication defaults to `auto`:

- if `[local_users]` is present in Streamlit secrets, the login gate uses local accounts
- otherwise, if `[ldap]` is present, the login gate uses LDAP
- if neither is present, local development opens the BI directly
- set `AUTH_PROVIDER = "local"` or `AUTH_PROVIDER = "ldap"` to force a provider
- set `AUTH_ENABLED = false` for trusted local smoke tests only

Start from the checked-in template:

```powershell
Copy-Item .streamlit\secrets.example.toml .streamlit\secrets.toml
```

Then replace the users, password hashes, cookie key, and optional authorization
rules. `.streamlit/secrets.toml` is ignored by git and must never be committed.

Minimum local-account Streamlit secrets:

```toml
AUTH_ENABLED = true
AUTH_PROVIDER = "local"

[local_users."user@example.com"]
name = "User Name"
role = "admin"
permissions = ["*"]
password_hash = "pbkdf2_sha256$260000$..."

[auth]
allowed_domains = ["example.com"]
allowed_users = []
```

Generate a password hash locally:

```powershell
python -c "from auth import make_password_hash; print(make_password_hash('replace-with-password'))"
```

Export permission is controlled by the `permissions` list:

- `["viewer"]`: can view pages, charts, and tables, but export buttons are hidden
- `["user"]`: can view and export
- `["*"]`: full export access

Optional LDAP secrets:

```toml
AUTH_ENABLED = true
AUTH_PROVIDER = "ldap"

[ldap]
server_path = "ldap://ldap.example.com"
domain = "example"
search_base = "dc=example,dc=com"
attributes = ["sAMAccountName", "distinguishedName", "userPrincipalName", "mail", "displayName", "manager", "title"]
use_ssl = true

[auth_cookie]
name = "anz_bi_login_cookie"
key = "replace-with-a-long-random-cookie-signing-key"
expiry_days = 1
auto_renewal = true
delay_sec = 0.1

[auth]
allowed_domains = ["example.com"]
allowed_users = []
```

Optional `SigninFormConfig` / `SignoutFormConfig` overrides can be added under
`[signin_form]` and `[signout_form]`; nested keys are merged with the default
Chinese login form labels.

## Exports

Each BI page has two filtered exports:

- provider execution list: no `merchant_id`, `institution_id`, or other internal lookup IDs
- internal record list: includes MID / merchant IDs and institution IDs for follow-up lookup in internal systems

## New Intake Default View

The New Intake page opens as an operational working view:

- cohort month range defaults to the latest 6 available months
- `圳兴商户` defaults to `排除圳兴`
- `线上渠道` defaults to `排除线上`

These are UI defaults only. The underlying private data still contains the full reviewed
New Intake contract, and users can include 圳兴 or ONLINE again from the sidebar.

For Streamlit Cloud, configure secrets:

```toml
DATA_BACKEND = "github_private"
DATA_GITHUB_REPO = "KenX31/anzdata"
DATA_GITHUB_REF = "main"
DATA_PROJECT = "anz-bi-platform"
DATA_GEO_PROJECT = "anz-geography"
DATA_KA_PROJECT = "anz-ka-dimension"
DATA_AMOUNT_UNIT = "minor"
DATA_GITHUB_TOKEN = "..."
```

`DATA_GITHUB_TOKEN` should be a GitHub fine-grained token or classic PAT that can
read repository contents from the private `KenX31/anzdata` repo. Keep it only in
Streamlit Secrets; never commit it to this code repository.

`DATA_AMOUNT_UNIT` defaults to `minor`, because current private BI data stores
`txn_amount_*` and `trade_amt_*` fields in cents/fen-style minor units. The app
divides amount fields by `100` at load time for KPI tables, charts, and exports.
If a future data refresh writes amounts already in major currency units, set this
secret to `major` before deploying that contract.

## Build Private Data Package

From this repo:

```powershell
python scripts\build_private_data_project.py `
  --output-root "D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform"
```

The script copies only reviewed processed outputs from the local analysis workspace and
writes a manifest with schema versions, row counts, source periods, and privacy levels.

The `anz-bi-platform` data project is page-scoped:

```text
projects/anz-bi-platform/
  manifest.json
  processed/
    new_intake/
    activation_low_activity/
    rate_coupon_activity/
    silent_merchants/
    shared_dimensions/
```

Each page owns its own `processed/<page_id>/` folder and `manifest.page_datasets`
entry. Future refreshes should update only the changed page folder plus the manifest
entry for that page, leaving unrelated BI pages untouched. Shared dimensions under
`processed/shared_dimensions/` should be small contracts used by the BI app itself;
reusable geo dimensions stay in the separate `anz-geography` project.

For a page-scoped Silent Merchants refresh only:

```powershell
python scripts\build_private_data_project.py `
  --silent-only `
  --output-root "D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform" `
  --silent-detail "D:\Tencent\Data analysis\2026.5.18_ANZ_silent_merchants_activation\data\raw\first_600.xlsx" `
  --silent-aggregate "D:\Tencent\Data analysis\2026.5.18_ANZ_silent_merchants_activation\data\raw\00a.xlsx"
```

For a page-scoped Rate Coupon Activity refresh only:

```powershell
python scripts\materialize_rate_coupon_activity.py `
  --output-root "D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform" `
  --source-monthly "D:\Tencent\Data analysis\2026.5.15_NZ_rate_coupon_stock_monthly\data\raw\rate_coupon_stock_from_start_to_202604_monthly.csv" `
  --version "2026.05.19-rate-coupon-v1"
```

The script writes only `processed/rate_coupon_activity/` and the
`manifest.page_datasets.rate_coupon_activity` entry. It keeps internal file
contracts, page ids, and metric keys in English ASCII; Chinese campaign names
are preserved only as display labels.

## Country-Aware Geography Contract

AU and NZ do not share the same operating geography hierarchy, so the app does not
force AU merchants into the NZ `geo_area` / `business_cluster` model.

The shared Streamlit interface is a reporting bridge:

```text
geo_country
geo_state
geo_city
geo_suburb
geo_postcode
nz_geo_area
nz_business_cluster
au_service_area
geo_reporting_level
geo_reporting_level_label
geo_reporting_name
```

Rules:

- NZ keeps `geo_area` and `business_cluster` as country-specific fields.
- If reviewed staging columns such as `staging_geo_area` are present, they take
  precedence over legacy prepared fields in the Streamlit reporting bridge.
- AU uses `au_service_area` when a reviewed AU operating area exists; otherwise the
  reporting fallback is city, then state, suburb, postcode, country.
- Mixed AU/NZ sidebar views expose only shared geography filters such as country and city.
- Selecting only NZ exposes City first. `NZ geo area` stays disabled until at least
  one City is selected, and it only enables when the selected City has reviewed
  `nz_geo_area` values.
- Selecting only AU exposes State / City / Suburb / Postcode.
- Charts and area ranking use `geo_reporting_level` + `geo_reporting_name` so the UI
  can be shared without pretending the two countries have identical dimensions.

The private data build writes the non-sensitive bridge contract to:

```text
processed/shared_dimensions/geo_reporting_bridge.csv
```

For local QA on this workstation, the app also reads the staging matcher directly
when `LOCAL_GEO_STAGING_ROOT` exists, defaulting to:

```text
D:\Tencent\Data analysis\ANZ_Data_Warehouse\data\Geo_warehouse_streamlit_staging
```

This lets localhost reflect the reviewed staging geography before the private data
repo is rebuilt. Deployment should still use reviewed processed files from
`KenX31/anzdata`.

For deployment, the reviewed geo dimensions are intentionally stored as a separate
private data project so other BI pages can reuse the same geo layer:

```text
KenX31/anzdata
projects/anz-bi-platform/
  manifest.json
  processed/new_intake/
  processed/activation_low_activity/
  processed/shared_dimensions/geo_reporting_bridge.csv
projects/anz-geography/
  manifest.json
  processed/
    nz_geo_dimension.csv
    nz_geo_area_rules.csv
    au_geo_dimension.csv
    au_geo_match_rules.csv
    geo_merchant_location_aliases.csv
```

The app reads BI page rows from `DATA_PROJECT` and the reviewed geo dimensions from
`DATA_GEO_PROJECT`. If the BI page rows do not include `staging_*` columns, the app
loads `projects/anz-geography/processed/*.csv` and applies the matcher at runtime.
`geo_merchant_location_aliases.csv` is a reviewed correction layer for chain-store
or multi-branch merchants whose registered address points to a headquarters or
payment-institution address while the branch location is encoded in
`merchant_short_name`.

The KA / SMB sidebar filter reads the shared KA merchant MID dimension from
`DATA_KA_PROJECT`, defaulting to `projects/anz-ka-dimension/processed/dim_ka_merchant_anz.csv`.
Rows whose `merchant_id` appears as `ka_mid` are treated as `KA`; all other rows are
treated as `SMB`.

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

Interpretation: the staging geo layer is better for city/suburb matching, especially Activation. It should not directly replace the current NZ business-area/cluster enrichment, because the AU skinny table intentionally omits business-area and cluster fields. Use the country-aware reporting bridge above when mapping geography into Streamlit.
