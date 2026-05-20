from __future__ import annotations

import json
import os
import base64
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

from data_io import duckdb_parquet_columns, duckdb_query_parquet_path, read_local_table, read_table_bytes, table_path_candidates
from geo_matching import MERCHANT_LOCATION_ALIAS_FILENAME, StreamlitGeoMatcher, append_staging_geo_columns
from geography import with_reporting_geography


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
    "month_label": "string",
    "snapshot_ds": "string",
    "merchant_id": "string",
    "institution_id": "string",
    "merchant_country_code": "string",
    "mcc_code": "string",
    "mcc": "string",
    "ka_mid": "string",
    "stock_id": "string",
    "stock_key": "string",
    "country_group": "string",
}
EXPECTED_SCHEMA = {
    "new_intake": "1.0",
    "activation_low_activity": "1.0",
    "rate_coupon_activity": "1.0",
    "silent_merchants": "1.0",
}
EXPECTED_GEO_CONTRACT = "country-aware-1.0"
NEW_INTAKE_ROWS_PATH = "processed/new_intake/new_intake_rows.csv"
ACTIVATION_ROWS_PATH = "processed/activation_low_activity/activation_candidates.csv"
SILENT_ROWS_PATH = "processed/silent_merchants/silent_merchants_rows.csv"
NEW_INTAKE_FILTER_COLUMNS = (
    "intake_month",
    "merchant_id",
    "merchant_company_name",
    "merchant_short_name",
    "institution_id",
    "institution_name",
    "institution_standard",
    "analysis_country",
    "country_group",
    "merchant_country_code",
    "geo_country",
    "geo_state",
    "geo_city",
    "geo_suburb",
    "geo_postcode",
    "nz_geo_area",
    "nz_business_cluster",
    "geo_reporting_level",
    "geo_reporting_name",
    "channel_type",
    "mcc_major_industry",
    "active_30d_flag",
    "is_zhenxing",
    "state",
    "business_state",
    "postcode",
    "au_service_area",
    "service_area",
    "business_city",
    "business_suburb",
    "geo_area",
    "business_cluster",
    "staging_country",
    "staging_state",
    "staging_city",
    "staging_suburb",
    "staging_geo_area",
    "staging_business_cluster",
    "staging_postcode",
)
ACTIVATION_FILTER_COLUMNS = (
    "merchant_id",
    "merchant_name",
    "merchant_short_name",
    "institution_id",
    "institution_name",
    "institution_group",
    "scope_country",
    "country_group",
    "merchant_country_code",
    "address",
    "normalized_address",
    "state",
    "business_state",
    "postcode",
    "au_service_area",
    "service_area",
    "business_city",
    "business_suburb",
    "geo_area",
    "business_cluster",
    "mcc",
    "mcc_name",
    "mcc_industry",
    "mcc_major_industry",
    "trade_cnt_prev_3m",
    "trade_cnt_prev_2m",
    "trade_cnt_prev_1m",
    "eligible_low_activity_flag",
    "decay_band",
    "activity_decay_score",
    "candidate_rank",
    "priority_label",
    "geo_country",
    "geo_state",
    "geo_city",
    "geo_suburb",
    "geo_postcode",
    "nz_geo_area",
    "nz_business_cluster",
    "geo_reporting_level",
    "geo_reporting_name",
    "staging_country",
    "staging_state",
    "staging_city",
    "staging_suburb",
    "staging_geo_area",
    "staging_business_cluster",
    "staging_postcode",
)
SILENT_FILTER_COLUMNS = (
    "merchant_id",
    "merchant_display_name",
    "merchant_company_name",
    "merchant_short_name",
    "institution_id",
    "institution_name",
    "institution_group",
    "country_group",
    "merchant_country_code",
    "state",
    "business_state",
    "postcode",
    "business_city",
    "business_suburb",
    "geo_area",
    "business_cluster",
    "geo_country",
    "geo_state",
    "geo_city",
    "geo_suburb",
    "geo_postcode",
    "nz_geo_area",
    "nz_business_cluster",
    "geo_reporting_level",
    "geo_reporting_name",
    "silence_tier",
    "access_age_band",
    "merchant_access_time",
    "business_type",
    "mcc_code",
    "mcc",
    "mcc_name",
    "mcc_industry",
    "mcc_major_industry",
    "address",
    "stores_address",
    "has_address_flag",
    "txn_count_360d",
    "txn_amount_360d",
    "staging_country",
    "staging_state",
    "staging_city",
    "staging_suburb",
    "staging_geo_area",
    "staging_business_cluster",
    "staging_postcode",
)
NEW_INTAKE_TEXT_COLUMNS = (
    "merchant_id",
    "merchant_company_name",
    "merchant_short_name",
    "institution_standard",
    "institution_name",
    "geo_reporting_name",
    "geo_city",
    "geo_suburb",
)


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


@dataclass(frozen=True)
class NewIntakeQuery:
    source: DataSource
    data_version: str

    def filter_frame(self) -> pd.DataFrame:
        return _load_new_intake_filter_frame_cached(self.source, self.data_version)

    def rows(self, criteria: dict[str, Any]) -> pd.DataFrame:
        criteria_key = json.dumps(criteria, ensure_ascii=False, sort_keys=True, default=str)
        return _load_new_intake_rows_filtered_cached(self.source, self.data_version, criteria_key)


@dataclass(frozen=True)
class ActivationLowActivityQuery:
    source: DataSource
    data_version: str

    def filter_frame(self) -> pd.DataFrame:
        return _load_activation_filter_frame_cached(self.source, self.data_version)

    def rows(self, criteria: dict[str, Any]) -> pd.DataFrame:
        criteria_key = json.dumps(criteria, ensure_ascii=False, sort_keys=True, default=str)
        return _load_activation_rows_filtered_cached(self.source, self.data_version, criteria_key)


@dataclass(frozen=True)
class SilentMerchantsQuery:
    source: DataSource
    data_version: str

    def filter_frame(self) -> pd.DataFrame:
        return _load_silent_filter_frame_cached(self.source, self.data_version)

    def rows(self, criteria: dict[str, Any]) -> pd.DataFrame:
        criteria_key = json.dumps(criteria, ensure_ascii=False, sort_keys=True, default=str)
        return _load_silent_rows_filtered_cached(self.source, self.data_version, criteria_key)


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


def load_project_manifest() -> dict[str, Any]:
    source = resolve_data_source()
    return _load_project_manifest_cached(source)


@st.cache_data(show_spinner=False, max_entries=16)
def _load_project_manifest_cached(source: DataSource) -> dict[str, Any]:
    manifest = _load_json(source, "manifest.json")
    return {"manifest": manifest}


@st.cache_resource(show_spinner=False, max_entries=2)
def _load_page_data_cached(source: DataSource, page: str, data_version: str) -> dict[str, Any]:
    if page == "new_intake":
        return _load_new_intake_data(source, data_version=data_version)
    if page == "activation_low_activity":
        return _load_activation_low_activity_data(source, data_version=data_version)
    if page == "silent_merchants":
        return _load_silent_merchants_data(source, data_version=data_version)
    if page == "rate_coupon_activity":
        return _load_rate_coupon_activity_data(source)
    raise DataLoadError(f"Unsupported page key: {page}")


def load_page_data(page: str) -> dict[str, Any]:
    source = resolve_data_source()
    manifest = _load_json(source, "manifest.json")
    ka_manifest = _load_project_json_optional(source, source.github_ka_project, "manifest.json")
    data_version = _page_data_version(manifest, ka_manifest, page)
    return _load_page_data_cached(source, page, data_version)


def load_project_data() -> dict[str, Any]:
    """Load the full project for compatibility; the app uses page-level loading."""

    source = resolve_data_source()
    manifest = _load_json(source, "manifest.json")
    project = {
        "new_intake": _load_new_intake_data(source),
        "activation_low_activity": _load_activation_low_activity_data(source),
        "silent_merchants": _load_silent_merchants_data(source),
        "rate_coupon_activity": _load_rate_coupon_activity_data(source),
        "shared_dimensions": {
            "geo_reporting_bridge": _load_frame_optional(source, "processed/shared_dimensions/geo_reporting_bridge.csv"),
            "ka_merchants": _load_ka_dimension(source),
        },
    }
    return {"manifest": manifest, **project}


def _page_data_version(manifest: dict[str, Any], ka_manifest: dict[str, Any], page: str) -> str:
    page_datasets = manifest.get("page_datasets") if isinstance(manifest.get("page_datasets"), dict) else {}
    page_info = page_datasets.get(page) if isinstance(page_datasets, dict) else {}
    page_info = page_info if isinstance(page_info, dict) else {}
    ka_version = ka_manifest.get("version") if page in {"new_intake", "activation_low_activity", "silent_merchants"} else ""
    return "|".join(
        str(part or "")
        for part in (
            manifest.get("version"),
            page,
            page_info.get("schema_version"),
            page_info.get("storage_format"),
            page_info.get("source_period"),
            page_info.get("row_count"),
            page_info.get("files"),
            ka_version,
        )
    )


def _load_new_intake_data(source: DataSource, *, data_version: str = "") -> dict[str, Any]:
    ka_dimension = _load_ka_dimension(source)
    base = {
        "summary": _load_json(source, "processed/new_intake/new_intake_summary.json"),
        "institution_rollup": _load_frame(source, "processed/new_intake/new_intake_institution_rollup.csv"),
    }
    if _new_intake_query_available(source):
        return {**base, "query": NewIntakeQuery(source, data_version)}
    return {
        **base,
        "rows": _append_ka_segment(
            _load_page_rows(source, NEW_INTAKE_ROWS_PATH),
            ka_dimension,
        ),
    }


def _new_intake_query_available(source: DataSource) -> bool:
    try:
        _resolve_project_parquet_path(source, source.github_project, NEW_INTAKE_ROWS_PATH)
    except DataLoadError:
        return False
    return True


@st.cache_data(show_spinner=False, max_entries=8)
def _load_new_intake_filter_frame_cached(source: DataSource, data_version: str) -> pd.DataFrame:
    del data_version
    frame = _query_project_parquet_frame(source, source.github_project, NEW_INTAKE_ROWS_PATH, columns=list(NEW_INTAKE_FILTER_COLUMNS))
    frame = _maybe_apply_geo_staging(source, frame)
    return _append_ka_segment(frame, _load_ka_dimension(source))


@st.cache_data(show_spinner=False, max_entries=48)
def _load_new_intake_rows_filtered_cached(source: DataSource, data_version: str, criteria_key: str) -> pd.DataFrame:
    del data_version
    criteria = json.loads(criteria_key) if criteria_key else {}
    parquet_path = _resolve_project_parquet_path(source, source.github_project, NEW_INTAKE_ROWS_PATH)
    available_columns = set(duckdb_parquet_columns(parquet_path))
    where_sql, parameters = _new_intake_where_sql(criteria, available_columns)
    frame = duckdb_query_parquet_path(parquet_path, where_sql=where_sql, parameters=parameters)
    frame = _normalize_amount_units(frame, source.amount_unit)
    frame = _maybe_apply_geo_staging(source, frame)
    frame = _append_ka_segment(frame, _load_ka_dimension(source))
    frame = with_reporting_geography(frame, country_columns=["analysis_country", "country_group", "merchant_country_code"])
    return _apply_new_intake_residual_filters(frame, criteria)


def _query_project_parquet_frame(
    source: DataSource,
    project: str,
    relative_path: str,
    *,
    columns: list[str] | None = None,
    where_sql: str = "",
    parameters: tuple[Any, ...] = (),
) -> pd.DataFrame:
    parquet_path = _resolve_project_parquet_path(source, project, relative_path)
    selected_columns = columns
    if columns:
        available = set(duckdb_parquet_columns(parquet_path))
        selected_columns = [column for column in columns if column in available]
    return duckdb_query_parquet_path(
        parquet_path,
        columns=selected_columns,
        where_sql=where_sql,
        parameters=parameters,
    )


def _resolve_project_parquet_path(source: DataSource, project: str, relative_path: str) -> Path:
    candidates = [candidate for candidate in table_path_candidates(relative_path) if Path(candidate).suffix.casefold() == ".parquet"]
    if source.backend == "local":
        for candidate in candidates:
            path = _local_project_path(source, project, candidate)
            if path.exists():
                return path
        raise DataLoadError(f"Missing local parquet data file for {relative_path}")
    if source.backend == "github_private":
        last_missing: DataLoadError | None = None
        for candidate in candidates:
            try:
                return _materialize_github_project_parquet(source, project, candidate)
            except DataLoadError as exc:
                if _is_not_found(exc):
                    last_missing = exc
                    continue
                raise
        if last_missing is not None:
            raise last_missing
        raise DataLoadError(f"Private parquet data file not found on GitHub: {relative_path}")
    raise DataLoadError(f"Unsupported DATA_BACKEND: {source.backend}")


@st.cache_resource(show_spinner=False, max_entries=64)
def _materialize_github_project_parquet(source: DataSource, project: str, relative_path: str) -> Path:
    payload = _read_github_project_bytes(source, project, relative_path)
    payload_hash = hashlib.sha256(payload).hexdigest()
    key = "|".join((source.github_repo, source.github_ref, project, relative_path, payload_hash))
    name = hashlib.sha256(key.encode("utf-8")).hexdigest()
    cache_root = Path(tempfile.gettempdir()) / "anzbi_parquet_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    path = cache_root / f"{name}.parquet"
    if not path.exists():
        path.write_bytes(payload)
    return path


def _new_intake_where_sql(criteria: dict[str, Any], available_columns: set[str]) -> tuple[str, tuple[Any, ...]]:
    clauses: list[str] = []
    parameters: list[Any] = []

    month_range = criteria.get("month_range")
    if "intake_month" in available_columns and isinstance(month_range, list | tuple) and len(month_range) == 2:
        start_key = _new_intake_month_key(month_range[0])
        end_key = _new_intake_month_key(month_range[1])
        if start_key > end_key:
            start_key, end_key = end_key, start_key
        clauses.append(f"{_new_intake_month_key_sql('intake_month')} between ? and ?")
        parameters.extend([start_key, end_key])

    in_sql, in_parameters = _in_filters_where_sql(criteria, available_columns)
    if in_sql:
        clauses.append(in_sql)
        parameters.extend(in_parameters)

    zhenxing_scope = str(criteria.get("zhenxing_scope") or "all")
    if "is_zhenxing" in available_columns:
        if zhenxing_scope == "only":
            clauses.append("coalesce(try_cast(\"is_zhenxing\" as double), 0) = 1")
        elif zhenxing_scope == "exclude":
            clauses.append("coalesce(try_cast(\"is_zhenxing\" as double), 0) <> 1")

    online_scope = str(criteria.get("online_scope") or "all")
    if "channel_type" in available_columns:
        if online_scope == "only":
            clauses.append("upper(coalesce(cast(\"channel_type\" as varchar), '')) = 'ONLINE'")
        elif online_scope == "exclude":
            clauses.append("upper(coalesce(cast(\"channel_type\" as varchar), '')) <> 'ONLINE'")

    active_status = str(criteria.get("active_status") or "all")
    if "active_30d_flag" in available_columns:
        if active_status == "active":
            clauses.append("cast(\"active_30d_flag\" as varchar) = '1'")
        elif active_status == "inactive":
            clauses.append("cast(\"active_30d_flag\" as varchar) = '0'")

    return " and ".join(clauses), tuple(parameters)


def _in_filters_where_sql(criteria: dict[str, Any], available_columns: set[str]) -> tuple[str, tuple[Any, ...]]:
    clauses: list[str] = []
    parameters: list[Any] = []
    in_filters = criteria.get("in_filters") if isinstance(criteria.get("in_filters"), dict) else {}
    for column, selected in in_filters.items():
        if column not in available_columns or not isinstance(selected, list):
            continue
        values = [str(value) for value in selected if str(value)]
        if not values:
            continue
        placeholders = ", ".join("?" for _ in values)
        clauses.append(f"cast({_quote_identifier(column)} as varchar) in ({placeholders})")
        parameters.extend(values)
    return " and ".join(clauses), tuple(parameters)


def _apply_new_intake_residual_filters(frame: pd.DataFrame, criteria: dict[str, Any]) -> pd.DataFrame:
    text_query = str(criteria.get("text_query") or "").strip().casefold()
    if text_query:
        existing = [column for column in NEW_INTAKE_TEXT_COLUMNS if column in frame.columns]
        if existing:
            mask = pd.Series(False, index=frame.index)
            for column in existing:
                mask = mask | frame[column].fillna("").astype(str).str.casefold().str.contains(text_query, regex=False)
            frame = frame[mask]

    ka_scope = str(criteria.get("ka_scope") or "all")
    if ka_scope == "all":
        return frame
    if "merchant_segment" in frame.columns:
        segment = frame["merchant_segment"].fillna("").astype(str).str.upper()
        is_ka = segment.eq("KA")
    elif "is_ka" in frame.columns:
        is_ka = pd.to_numeric(frame["is_ka"], errors="coerce").fillna(0).astype(int).eq(1)
    else:
        return frame
    if ka_scope == "only":
        return frame[is_ka]
    if ka_scope == "exclude":
        return frame[~is_ka]
    return frame


def _new_intake_month_key(value: object) -> int:
    text = str(value or "").strip().replace("-", ".").replace("/", ".")
    parts = text.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        month = 10 if parts[1] == "1" else int(parts[1])
        if 1 <= month <= 12:
            return int(parts[0]) * 100 + month
    return 999999


def _new_intake_month_key_sql(column: str) -> str:
    column_sql = f"cast({_quote_identifier(column)} as varchar)"
    normalized = f"replace(replace({column_sql}, '/', '.'), '-', '.')"
    year_sql = f"try_cast(split_part({normalized}, '.', 1) as integer)"
    month_text_sql = f"split_part({normalized}, '.', 2)"
    month_sql = f"case when {month_text_sql} = '1' then 10 else try_cast({month_text_sql} as integer) end"
    return f"coalesce(({year_sql} * 100 + {month_sql}), 999999)"


def _load_activation_low_activity_data(source: DataSource, *, data_version: str = "") -> dict[str, Any]:
    ka_dimension = _load_ka_dimension(source)
    base = {
        "summary": _load_json(source, "processed/activation_low_activity/low_activity_bi_summary.json"),
        "area_rollup": _load_frame(source, "processed/activation_low_activity/area_low_activity_rollup.csv"),
    }
    if _activation_query_available(source):
        return {**base, "query": ActivationLowActivityQuery(source, data_version)}
    return {
        **base,
        "rows": _append_ka_segment(
            _load_page_rows(source, ACTIVATION_ROWS_PATH),
            ka_dimension,
        ),
    }


def _activation_query_available(source: DataSource) -> bool:
    try:
        _resolve_project_parquet_path(source, source.github_project, ACTIVATION_ROWS_PATH)
    except DataLoadError:
        return False
    return True


@st.cache_data(show_spinner=False, max_entries=8)
def _load_activation_filter_frame_cached(source: DataSource, data_version: str) -> pd.DataFrame:
    del data_version
    frame = _query_project_parquet_frame(
        source,
        source.github_project,
        ACTIVATION_ROWS_PATH,
        columns=list(ACTIVATION_FILTER_COLUMNS),
    )
    frame = _normalize_amount_units(frame, source.amount_unit)
    frame = _maybe_apply_geo_staging(source, frame)
    frame = _append_ka_segment(frame, _load_ka_dimension(source))
    return with_reporting_geography(frame, country_columns=["scope_country", "country_group", "merchant_country_code"])


@st.cache_data(show_spinner=False, max_entries=48)
def _load_activation_rows_filtered_cached(source: DataSource, data_version: str, criteria_key: str) -> pd.DataFrame:
    del data_version
    criteria = json.loads(criteria_key) if criteria_key else {}
    parquet_path = _resolve_project_parquet_path(source, source.github_project, ACTIVATION_ROWS_PATH)
    available_columns = set(duckdb_parquet_columns(parquet_path))
    where_sql, parameters = _in_filters_where_sql(criteria, available_columns)
    frame = duckdb_query_parquet_path(parquet_path, where_sql=where_sql, parameters=parameters)
    frame = _normalize_amount_units(frame, source.amount_unit)
    frame = _maybe_apply_geo_staging(source, frame)
    frame = _append_ka_segment(frame, _load_ka_dimension(source))
    return with_reporting_geography(frame, country_columns=["scope_country", "country_group", "merchant_country_code"])


def _load_silent_merchants_data(source: DataSource, *, data_version: str = "") -> dict[str, Any]:
    ka_dimension = _load_ka_dimension(source)
    base = {
        "summary": _load_json(source, "processed/silent_merchants/silent_merchants_summary.json"),
        "aggregate": _load_frame(source, "processed/silent_merchants/silent_merchants_aggregate.csv"),
    }
    if _silent_query_available(source):
        return {**base, "query": SilentMerchantsQuery(source, data_version)}
    return {
        **base,
        "rows": _append_ka_segment(
            _load_page_rows(source, SILENT_ROWS_PATH),
            ka_dimension,
        ),
    }


def _silent_query_available(source: DataSource) -> bool:
    try:
        _resolve_project_parquet_path(source, source.github_project, SILENT_ROWS_PATH)
    except DataLoadError:
        return False
    return True


@st.cache_data(show_spinner=False, max_entries=8)
def _load_silent_filter_frame_cached(source: DataSource, data_version: str) -> pd.DataFrame:
    del data_version
    frame = _query_project_parquet_frame(
        source,
        source.github_project,
        SILENT_ROWS_PATH,
        columns=list(SILENT_FILTER_COLUMNS),
    )
    frame = _normalize_amount_units(frame, source.amount_unit)
    frame = _maybe_apply_geo_staging(source, frame)
    frame = _append_ka_segment(frame, _load_ka_dimension(source))
    return with_reporting_geography(frame, country_columns=["country_group", "merchant_country_code"])


@st.cache_data(show_spinner=False, max_entries=48)
def _load_silent_rows_filtered_cached(source: DataSource, data_version: str, criteria_key: str) -> pd.DataFrame:
    del data_version
    criteria = json.loads(criteria_key) if criteria_key else {}
    parquet_path = _resolve_project_parquet_path(source, source.github_project, SILENT_ROWS_PATH)
    available_columns = set(duckdb_parquet_columns(parquet_path))
    where_sql, parameters = _in_filters_where_sql(criteria, available_columns)
    frame = duckdb_query_parquet_path(parquet_path, where_sql=where_sql, parameters=parameters)
    frame = _normalize_amount_units(frame, source.amount_unit)
    frame = _maybe_apply_geo_staging(source, frame)
    frame = _append_ka_segment(frame, _load_ka_dimension(source))
    return with_reporting_geography(frame, country_columns=["country_group", "merchant_country_code"])


def _load_rate_coupon_activity_data(source: DataSource) -> dict[str, Any]:
    return {
        "monthly": _load_frame(source, "processed/rate_coupon_activity/rate_coupon_monthly.csv"),
        "stock_metadata": _load_frame(source, "processed/rate_coupon_activity/rate_coupon_stock_metadata.csv"),
        "summary": _load_json(source, "processed/rate_coupon_activity/rate_coupon_summary.json"),
    }


def validate_project(project: dict[str, Any]) -> None:
    validate_project_metadata(project)

    for page, expected in EXPECTED_SCHEMA.items():
        validate_page_dataset(project, page, expected_schema=expected)


def validate_project_metadata(project: dict[str, Any]) -> None:
    manifest = project.get("manifest") or {}
    if manifest.get("project_id") != PROJECT_ID:
        raise DataLoadError(
            f"Loaded data project is {manifest.get('project_id')!r}; expected {PROJECT_ID!r}."
        )

    shared_dimensions = manifest.get("shared_dimensions") or {}
    geo_contract = (shared_dimensions.get("geo_reporting_bridge") or {}).get("schema_version")
    if geo_contract and str(geo_contract) != EXPECTED_GEO_CONTRACT:
        raise DataLoadError(
            f"geo_reporting_bridge schema version is {geo_contract}; expected {EXPECTED_GEO_CONTRACT}. "
            "Please refresh the private data package before rendering this app."
        )


def validate_page_dataset(
    project: dict[str, Any],
    page: str,
    *,
    expected_schema: str | None = None,
) -> None:
    manifest = project.get("manifest") or {}
    page_datasets = manifest.get("page_datasets") or {}
    expected = expected_schema or EXPECTED_SCHEMA.get(page)
    if expected is None:
        raise DataLoadError(
            f"Unsupported page key: {page}"
        )
    actual = str((page_datasets.get(page) or {}).get("schema_version") or "")
    if actual != expected:
        raise DataLoadError(
            f"{page} schema version is {actual or 'missing'}; expected {expected}. "
            "Please refresh the private data package before rendering this page."
        )


@st.cache_data(show_spinner=False, max_entries=96)
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
    frame = _load_project_frame(source, source.github_project, relative_path)
    return _normalize_amount_units(frame, source.amount_unit)


def _load_project_frame(source: DataSource, project: str, relative_path: str) -> pd.DataFrame:
    if source.backend == "local":
        path = _local_project_path(source, project, relative_path)
        try:
            return read_local_table(path, csv_dtypes=CSV_DTYPES)
        except FileNotFoundError:
            candidates = ", ".join(table_path_candidates(relative_path))
            raise DataLoadError(f"Missing local data file for {path}; checked {candidates}") from None
    if source.backend == "github_private":
        return _load_github_project_frame(source, project, relative_path)
    raise DataLoadError(f"Unsupported DATA_BACKEND: {source.backend}")


def _load_github_project_frame(source: DataSource, project: str, relative_path: str) -> pd.DataFrame:
    last_missing: DataLoadError | None = None
    for candidate in table_path_candidates(relative_path):
        try:
            payload = _read_github_project_bytes(source, project, candidate)
        except DataLoadError as exc:
            if _is_not_found(exc):
                last_missing = exc
                continue
            raise
        try:
            return read_table_bytes(payload, relative_path=candidate, csv_dtypes=CSV_DTYPES)
        except Exception as exc:
            raise DataLoadError(f"Could not read table {candidate}: {exc}") from exc
    if last_missing is not None:
        raise last_missing
    raise DataLoadError(f"Private data file not found on GitHub: {relative_path}")


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


@st.cache_data(show_spinner=False, max_entries=24)
def _load_geo_frame_optional(source: DataSource, relative_path: str) -> pd.DataFrame:
    try:
        return _load_project_frame(source, source.github_geo_project, relative_path)
    except DataLoadError:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, max_entries=8)
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
        return _load_project_frame(source, project, relative_path)
    except DataLoadError:
        return pd.DataFrame()


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


def _read_project_bytes(source: DataSource, project: str, relative_path: str) -> bytes:
    if source.backend == "local":
        path = _local_project_path(source, project, relative_path)
        if not path.exists():
            raise DataLoadError(f"Missing local data file: {path}")
        return path.read_bytes()
    if source.backend == "github_private":
        return _read_github_project_bytes(source, project, relative_path)
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
    return _read_github_project_bytes(source, project, relative_path).decode("utf-8-sig")


@st.cache_data(show_spinner=False, max_entries=256)
def _read_github_project_bytes(source: DataSource, project: str, relative_path: str) -> bytes:
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
        return _github_response_bytes(source, response, relative_path)

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
    return _github_response_bytes(source, response, relative_path).decode("utf-8-sig")


def _github_response_bytes(source: DataSource, response: requests.Response, relative_path: str) -> bytes:
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return response.content

    payload = response.json()
    if isinstance(payload, dict):
        encoded = str(payload.get("content") or "").strip()
        if encoded:
            return base64.b64decode(encoded)
        download_url = payload.get("download_url")
        if download_url:
            headers = {
                "Authorization": f"Bearer {source.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            raw = requests.get(str(download_url), headers=headers, timeout=30)
            if raw.ok:
                return raw.content
            raise DataLoadError(
                f"GitHub raw download failed for {relative_path}: HTTP {raw.status_code}"
            )
    raise DataLoadError(f"GitHub returned an unexpected response for {relative_path}.")


def _is_not_found(exc: DataLoadError) -> bool:
    return "not found" in str(exc).casefold() or "missing local data file" in str(exc).casefold()


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'
