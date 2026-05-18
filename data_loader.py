from __future__ import annotations

import json
import os
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

from geo_matching import MERCHANT_LOCATION_ALIAS_FILENAME, StreamlitGeoMatcher, append_staging_geo_columns


PROJECT_ID = "anz-bi-platform"
GEO_PROJECT_ID = "anz-geography"
KA_PROJECT_ID = "anz-ka-dimension"
DEFAULT_LOCAL_PROJECT_ROOT = Path(r"D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform")
DEFAULT_LOCAL_GEO_STAGING_ROOT = Path(
    r"D:\Tencent\Data analysis\ANZ_Data_Warehouse\data\Geo_warehouse_streamlit_staging"
)
REMOTE_GEO_ROOT = "processed"
CSV_DTYPES = {
    "intake_month": "string",
    "snapshot_ds": "string",
    "merchant_id": "string",
    "institution_id": "string",
    "merchant_country_code": "string",
    "mcc_code": "string",
    "mcc": "string",
    "ka_mid": "string",
}
EXPECTED_SCHEMA = {
    "new_intake": "1.0",
    "activation_low_activity": "1.0",
    "silent_merchants": "1.0",
}
EXPECTED_GEO_CONTRACT = "country-aware-1.0"


class DataLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataSource:
    backend: str
    local_root: Path | None = None
    geo_staging_root: Path | None = None
    github_repo: str = "KenX31/anzdata"
    github_ref: str = "main"
    github_project: str = PROJECT_ID
    github_geo_project: str = GEO_PROJECT_ID
    github_ka_project: str = KA_PROJECT_ID
    github_token: str = ""
    amount_unit: str = "minor"


def _secret_or_env(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        value = None
    return str(value or os.getenv(name, default))


def resolve_data_source() -> DataSource:
    backend = _secret_or_env("DATA_BACKEND", "").strip().lower()
    if not backend:
        backend = "local" if DEFAULT_LOCAL_PROJECT_ROOT.exists() else "github_private"
    local_root = _secret_or_env("LOCAL_DATA_ROOT", "")
    geo_staging_root = _secret_or_env("LOCAL_GEO_STAGING_ROOT", "")
    resolved_local_root = Path(local_root).expanduser() if local_root else None
    if backend == "local" and resolved_local_root is None and DEFAULT_LOCAL_PROJECT_ROOT.exists():
        resolved_local_root = DEFAULT_LOCAL_PROJECT_ROOT
    resolved_geo_staging_root = Path(geo_staging_root).expanduser() if geo_staging_root else None
    if backend == "local" and resolved_geo_staging_root is None and DEFAULT_LOCAL_GEO_STAGING_ROOT.exists():
        resolved_geo_staging_root = DEFAULT_LOCAL_GEO_STAGING_ROOT
    return DataSource(
        backend=backend,
        local_root=resolved_local_root,
        geo_staging_root=resolved_geo_staging_root,
        github_repo=_secret_or_env("DATA_GITHUB_REPO", "KenX31/anzdata"),
        github_ref=_secret_or_env("DATA_GITHUB_REF", "main"),
        github_project=_secret_or_env("DATA_PROJECT", PROJECT_ID),
        github_geo_project=_secret_or_env("DATA_GEO_PROJECT", GEO_PROJECT_ID),
        github_ka_project=_secret_or_env("DATA_KA_PROJECT", KA_PROJECT_ID),
        github_token=_secret_or_env("DATA_GITHUB_TOKEN", ""),
        amount_unit=_secret_or_env("DATA_AMOUNT_UNIT", "minor").strip().lower(),
    )


def load_project_data() -> dict[str, Any]:
    source = resolve_data_source()
    manifest = _load_json(source, "manifest.json")
    ka_manifest = _load_project_json_optional(source, source.github_ka_project, "manifest.json")
    data_version = f"{manifest.get('version') or ''}|ka:{ka_manifest.get('version') or ''}"
    project = _load_project_data_cached(source, data_version)
    return {"manifest": manifest, **project}


@st.cache_data(show_spinner=False)
def _load_project_data_cached(source: DataSource, data_version: str) -> dict[str, Any]:
    ka_dimension = _load_ka_dimension(source)
    return {
        "new_intake": {
            "rows": _append_ka_segment(
                _load_page_rows(source, "processed/new_intake/new_intake_rows.csv"),
                ka_dimension,
            ),
            "summary": _load_json(source, "processed/new_intake/new_intake_summary.json"),
            "institution_rollup": _load_frame(source, "processed/new_intake/new_intake_institution_rollup.csv"),
            "export_rows": _load_frame(source, "processed/new_intake/new_intake_export.csv"),
            "provider_export_rows": _load_frame_optional(source, "processed/new_intake/new_intake_provider_export.csv"),
            "internal_export_rows": _load_frame_optional(source, "processed/new_intake/new_intake_internal_record_export.csv"),
        },
        "activation_low_activity": {
            "rows": _append_ka_segment(
                _load_page_rows(source, "processed/activation_low_activity/activation_candidates.csv"),
                ka_dimension,
            ),
            "summary": _load_json(source, "processed/activation_low_activity/low_activity_bi_summary.json"),
            "area_rollup": _load_frame(source, "processed/activation_low_activity/area_low_activity_rollup.csv"),
            "export_rows": _load_frame(source, "processed/activation_low_activity/activation_export.csv"),
            "provider_export_rows": _load_frame_optional(source, "processed/activation_low_activity/activation_provider_export.csv"),
            "internal_export_rows": _load_frame_optional(source, "processed/activation_low_activity/activation_internal_record_export.csv"),
        },
        "silent_merchants": {
            "rows": _append_ka_segment(
                _load_page_rows(source, "processed/silent_merchants/silent_merchants_rows.csv"),
                ka_dimension,
            ),
            "summary": _load_json(source, "processed/silent_merchants/silent_merchants_summary.json"),
            "aggregate": _load_frame(source, "processed/silent_merchants/silent_merchants_aggregate.csv"),
            "export_rows": _load_frame(source, "processed/silent_merchants/silent_merchants_provider_export.csv"),
            "provider_export_rows": _load_frame_optional(source, "processed/silent_merchants/silent_merchants_provider_export.csv"),
            "internal_export_rows": _load_frame_optional(source, "processed/silent_merchants/silent_merchants_internal_record_export.csv"),
        },
        "shared_dimensions": {
            "geo_reporting_bridge": _load_frame_optional(source, "processed/shared_dimensions/geo_reporting_bridge.csv"),
            "ka_merchants": ka_dimension,
        },
    }


def validate_project(project: dict[str, Any]) -> None:
    manifest = project.get("manifest") or {}
    if manifest.get("project_id") != PROJECT_ID:
        raise DataLoadError(
            f"Loaded data project is {manifest.get('project_id')!r}; expected {PROJECT_ID!r}."
        )

    page_datasets = manifest.get("page_datasets") or {}
    for page, expected in EXPECTED_SCHEMA.items():
        actual = str((page_datasets.get(page) or {}).get("schema_version") or "")
        if actual != expected:
            raise DataLoadError(
                f"{page} schema version is {actual or 'missing'}; expected {expected}. "
                "Please refresh the private data package before rendering this app."
            )

    shared_dimensions = manifest.get("shared_dimensions") or {}
    geo_contract = (shared_dimensions.get("geo_reporting_bridge") or {}).get("schema_version")
    if geo_contract and str(geo_contract) != EXPECTED_GEO_CONTRACT:
        raise DataLoadError(
            f"geo_reporting_bridge schema version is {geo_contract}; expected {EXPECTED_GEO_CONTRACT}. "
            "Please refresh the private data package before rendering this app."
        )


def _load_json(source: DataSource, relative_path: str) -> dict[str, Any]:
    text = _read_text(source, relative_path)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataLoadError(f"Invalid JSON in {relative_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DataLoadError(f"{relative_path} must contain a JSON object.")
    return payload


def _load_frame(source: DataSource, relative_path: str) -> pd.DataFrame:
    if source.backend == "local":
        path = _local_path(source, relative_path)
        if not path.exists():
            raise DataLoadError(f"Missing local data file: {path}")
        return _normalize_amount_units(_read_csv_path(path), source.amount_unit)
    text = _read_text(source, relative_path)
    return _normalize_amount_units(_read_csv_text(text), source.amount_unit)


def _load_page_rows(source: DataSource, relative_path: str) -> pd.DataFrame:
    frame = _load_frame(source, relative_path)
    return _maybe_apply_geo_staging(source, frame)


def _maybe_apply_geo_staging(source: DataSource, frame: pd.DataFrame) -> pd.DataFrame:
    if "staging_geo_area" in frame.columns:
        return frame
    matcher = _resolve_geo_matcher(source)
    if matcher is None:
        return frame
    return append_staging_geo_columns(frame, matcher)


def _resolve_geo_matcher(source: DataSource) -> StreamlitGeoMatcher | None:
    if source.backend == "local":
        return _local_geo_matcher(source)
    if source.backend == "github_private":
        return _github_geo_matcher(source)
    return None


def _local_geo_matcher(source: DataSource) -> StreamlitGeoMatcher | None:
    if source.geo_staging_root is None:
        return None
    required = ("nz_geo_dimension.csv", "au_geo_dimension.csv")
    if not all((source.geo_staging_root / name).exists() for name in required):
        return None
    return StreamlitGeoMatcher(
        source.geo_staging_root,
        merchant_aliases=_load_local_geo_aliases(source),
    )


def _github_geo_matcher(source: DataSource) -> StreamlitGeoMatcher | None:
    nz = _load_geo_frame_optional(source, f"{REMOTE_GEO_ROOT}/nz_geo_dimension.csv")
    au = _load_geo_frame_optional(source, f"{REMOTE_GEO_ROOT}/au_geo_dimension.csv")
    if nz.empty or au.empty:
        return None
    return StreamlitGeoMatcher.from_frames(
        nz=nz,
        au=au,
        nz_rules=_load_geo_frame_optional(source, f"{REMOTE_GEO_ROOT}/nz_geo_area_rules.csv"),
        au_rules=_load_geo_frame_optional(source, f"{REMOTE_GEO_ROOT}/au_geo_match_rules.csv"),
        merchant_aliases=_load_geo_frame_optional(source, f"{REMOTE_GEO_ROOT}/{MERCHANT_LOCATION_ALIAS_FILENAME}"),
    )


def _load_local_geo_aliases(source: DataSource) -> pd.DataFrame:
    if source.geo_staging_root is not None:
        staging_path = source.geo_staging_root / MERCHANT_LOCATION_ALIAS_FILENAME
        if staging_path.exists():
            return _read_csv_path(staging_path)
    return _load_project_frame_optional(
        source,
        source.github_geo_project,
        f"{REMOTE_GEO_ROOT}/{MERCHANT_LOCATION_ALIAS_FILENAME}",
    )


def _load_frame_optional(source: DataSource, relative_path: str) -> pd.DataFrame:
    try:
        return _load_frame(source, relative_path)
    except DataLoadError:
        return pd.DataFrame()


def _load_geo_frame_optional(source: DataSource, relative_path: str) -> pd.DataFrame:
    try:
        text = _read_github_project_text(source, source.github_geo_project, relative_path)
    except DataLoadError:
        return pd.DataFrame()
    from io import StringIO

    return pd.read_csv(StringIO(text))


def _load_ka_dimension(source: DataSource) -> pd.DataFrame:
    frame = _load_project_frame_optional(source, source.github_ka_project, "processed/dim_ka_merchant_anz.csv")
    if frame.empty:
        return pd.DataFrame(columns=["ka_mid", "is_ka", "merchant_segment"])
    out = frame.copy()
    out["ka_mid"] = out["ka_mid"].fillna("").astype(str).str.strip()
    out = out[out["ka_mid"] != ""]
    out = out.drop_duplicates("ka_mid", keep="first")
    return out


def _append_ka_segment(rows: pd.DataFrame, ka_dimension: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    for column in (
        "is_ka",
        "merchant_segment",
        "ka_mid",
        "ka_country_group",
        "ka_group",
        "ka_brand",
        "ka_institution",
    ):
        if column in out.columns:
            out = out.drop(columns=column)
    if "merchant_id" not in out.columns or out.empty or ka_dimension.empty:
        return _with_default_smb_segment(out)

    dim_columns = [
        column
        for column in (
            "ka_mid",
            "is_ka",
            "merchant_segment",
            "country_group",
            "ka_group",
            "ka_brand",
            "ka_institution",
        )
        if column in ka_dimension.columns
    ]
    dim = ka_dimension[dim_columns].copy()
    dim["ka_mid"] = dim["ka_mid"].fillna("").astype(str).str.strip()
    dim = dim[dim["ka_mid"] != ""].drop_duplicates("ka_mid", keep="first")
    dim["_merchant_id_join"] = dim["ka_mid"]
    dim = dim.rename(columns={"country_group": "ka_country_group"})

    out["_merchant_id_join"] = out["merchant_id"].fillna("").astype(str).str.strip()
    out = out.merge(dim, how="left", on="_merchant_id_join")
    out = out.drop(columns="_merchant_id_join")
    out["ka_mid"] = out["ka_mid"].fillna("") if "ka_mid" in out.columns else ""
    is_ka = out["is_ka"] if "is_ka" in out.columns else pd.Series([0] * len(out), index=out.index)
    out["is_ka"] = pd.to_numeric(is_ka, errors="coerce").fillna(0).astype(int)
    out["merchant_segment"] = out["merchant_segment"].fillna("").astype(str)
    out.loc[out["is_ka"].eq(1), "merchant_segment"] = "KA"
    out.loc[~out["is_ka"].eq(1), "merchant_segment"] = "SMB"
    for column in ("ka_country_group", "ka_group", "ka_brand", "ka_institution"):
        if column in out.columns:
            out[column] = out[column].fillna("").astype(str)
        else:
            out[column] = ""
    return out


def _with_default_smb_segment(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    out["is_ka"] = 0
    out["merchant_segment"] = "SMB"
    out["ka_mid"] = ""
    out["ka_country_group"] = ""
    out["ka_group"] = ""
    out["ka_brand"] = ""
    out["ka_institution"] = ""
    return out


def _load_project_json_optional(source: DataSource, project: str, relative_path: str) -> dict[str, Any]:
    try:
        text = _read_project_text(source, project, relative_path)
    except DataLoadError:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_project_frame_optional(source: DataSource, project: str, relative_path: str) -> pd.DataFrame:
    try:
        text = _read_project_text(source, project, relative_path)
    except DataLoadError:
        return pd.DataFrame()
    return _read_csv_text(text)


def _read_csv_path(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=CSV_DTYPES)


def _read_csv_text(text: str) -> pd.DataFrame:
    from io import StringIO

    return pd.read_csv(StringIO(text), dtype=CSV_DTYPES)


def _normalize_amount_units(df: pd.DataFrame, amount_unit: str) -> pd.DataFrame:
    if df.empty or amount_unit not in {"minor", "cents", "fen"}:
        return df
    out = df.copy()
    for column in out.columns:
        if not _is_amount_column(column):
            continue
        values = pd.to_numeric(out[column], errors="coerce")
        out[column] = (values / 100).round(2)
    return out


def _is_amount_column(column: str) -> bool:
    name = str(column).lower()
    return "amount" in name or name.startswith("trade_amt") or name.startswith("txn_amt")


def _read_text(source: DataSource, relative_path: str) -> str:
    return _read_project_text(source, source.github_project, relative_path)


def _read_project_text(source: DataSource, project: str, relative_path: str) -> str:
    if source.backend == "local":
        path = _local_project_path(source, project, relative_path)
        if not path.exists():
            raise DataLoadError(f"Missing local data file: {path}")
        return path.read_text(encoding="utf-8-sig")
    if source.backend == "github_private":
        return _read_github_project_text(source, project, relative_path)
    raise DataLoadError(f"Unsupported DATA_BACKEND: {source.backend}")


def _local_path(source: DataSource, relative_path: str) -> Path:
    return _local_project_path(source, source.github_project, relative_path)


def _local_project_path(source: DataSource, project: str, relative_path: str) -> Path:
    root = source.local_root
    if root is None:
        raise DataLoadError(
            "LOCAL_DATA_ROOT is required when DATA_BACKEND=local. "
            f"Expected local project root like {DEFAULT_LOCAL_PROJECT_ROOT}."
        )
    if project != source.github_project:
        root = root.parent / project
    return root / relative_path


def _read_github_project_text(source: DataSource, project: str, relative_path: str) -> str:
    if not source.github_token:
        raise DataLoadError(
            "DATA_GITHUB_TOKEN is required when DATA_BACKEND=github_private. "
            "Create a GitHub token with read-only Contents access to KenX31/anzdata "
            "and add it in Streamlit app Secrets."
        )

    github_path = f"projects/{project}/{relative_path}"
    url = f"https://api.github.com/repos/{source.github_repo}/contents/{quote(github_path, safe='/')}"
    headers = {
        "Accept": "application/vnd.github.raw+json",
        "Authorization": f"Bearer {source.github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.get(url, headers=headers, params={"ref": source.github_ref}, timeout=30)
    if response.ok:
        return _github_response_text(source, response, relative_path)

    status = response.status_code
    if status in {401, 403}:
        raise DataLoadError(
            f"GitHub data request was denied for {relative_path}: HTTP {status}. "
            "Check DATA_GITHUB_TOKEN, token expiry, and read permission for KenX31/anzdata."
        )
    if status == 404:
        raise DataLoadError(
            f"Private data file not found on GitHub: {relative_path}. "
            f"Checked repo={source.github_repo}, ref={source.github_ref}, "
            f"project={project}."
        )
    raise DataLoadError(f"GitHub data request failed for {relative_path}: HTTP {status}")


def _github_response_text(source: DataSource, response: requests.Response, relative_path: str) -> str:
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return response.text

    payload = response.json()
    if isinstance(payload, dict):
        encoded = str(payload.get("content") or "").strip()
        if encoded:
            return base64.b64decode(encoded).decode("utf-8-sig")
        download_url = payload.get("download_url")
        if download_url:
            headers = {
                "Authorization": f"Bearer {source.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            raw = requests.get(str(download_url), headers=headers, timeout=30)
            if raw.ok:
                return raw.text
            raise DataLoadError(
                f"GitHub raw download failed for {relative_path}: HTTP {raw.status_code}"
            )
    raise DataLoadError(f"GitHub returned an unexpected response for {relative_path}.")
