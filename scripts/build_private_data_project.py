from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from exports import (  # noqa: E402
    activation_internal_export,
    activation_provider_export,
    new_intake_internal_export,
    new_intake_provider_export,
    silent_merchants_internal_export,
    silent_merchants_provider_export,
)
from geography import geo_reporting_bridge_contract, with_reporting_geography  # noqa: E402


PROJECT_ID = "anz-bi-platform"
VERSION = "2026.05.18-v1"
SCHEMA_VERSION = "1.0"
EXPORT_CONTRACT_VERSION = "1.1"
GEO_CONTRACT_VERSION = "country-aware-1.0"

DEFAULT_NEW_INTAKE_PREPARED = Path(
    r"D:\Tencent\Data analysis\Wechat-Pay-ANZ-MAP\tmp\new-intake-refresh-data\prepared\new-intake"
)
DEFAULT_ACTIVATION_PREPARED = Path(
    r"D:\Tencent\Data analysis\Wechat-Pay-ANZ-MAP\tmp\local-data\prepared\activation-map"
)
DEFAULT_SILENT_DETAIL = Path(
    r"D:\Tencent\Data analysis\2026.5.18_ANZ_silent_merchants_activation\data\raw\first_600.xlsx"
)
DEFAULT_SILENT_AGGREGATE = Path(
    r"D:\Tencent\Data analysis\2026.5.18_ANZ_silent_merchants_activation\data\raw\00a.xlsx"
)

NEW_INTAKE_FIELDS = [
    "intake_month",
    "merchant_id",
    "merchant_company_name",
    "merchant_short_name",
    "institution_id",
    "institution_name",
    "institution_standard",
    "merchant_country_code",
    "country_group",
    "analysis_country",
    "txn_count_30d",
    "txn_amount_30d",
    "active_30d_flag",
    "channel_type",
    "mcc_code",
    "mcc_major_industry",
    "store_address",
    "state",
    "business_state",
    "postcode",
    "au_service_area",
    "service_area",
    "business_city",
    "business_suburb",
    "geo_area",
    "business_cluster",
    "business_area",
    "is_zhenxing",
]

ACTIVATION_FIELDS = [
    "merchant_id",
    "merchant_name",
    "merchant_short_name",
    "institution_id",
    "institution_name",
    "institution_group",
    "scope_country",
    "address",
    "state",
    "business_state",
    "postcode",
    "au_service_area",
    "service_area",
    "business_city",
    "business_suburb",
    "geo_area",
    "business_cluster",
    "business_area",
    "mcc",
    "mcc_name",
    "mcc_industry",
    "mcc_major_industry",
    "trade_cnt_prev_3m",
    "trade_cnt_prev_2m",
    "trade_cnt_prev_1m",
    "trade_amt_prev_3m",
    "trade_amt_prev_2m",
    "trade_amt_prev_1m",
    "eligible_low_activity_flag",
    "decay_band",
    "recent_activity_band",
    "activity_decay_score",
    "candidate_rank",
]

ACTIVATION_PRIORITY_LABELS = {
    "severe": "严重下滑",
    "high": "明显下滑",
    "medium": "稍微下滑",
    "stable": "稳定",
}

SILENT_FIELDS = [
    "snapshot_ds",
    "country_group",
    "merchant_country_code",
    "merchant_id",
    "merchant_display_name",
    "merchant_company_name",
    "merchant_short_name",
    "institution_id",
    "institution_name",
    "institution_group",
    "business_type",
    "mcc_code",
    "merchant_state",
    "stores_number",
    "stores_address",
    "address",
    "website",
    "merchant_access_time",
    "profile_create_time",
    "profile_modify_time",
    "submch_manage_time",
    "txn_count_30d",
    "txn_amount_30d",
    "txn_count_180d",
    "txn_amount_180d",
    "txn_count_360d",
    "txn_amount_360d",
    "txn_count_720d",
    "txn_amount_720d",
    "silence_tier",
    "access_age_band",
    "has_address_flag",
    "field_visit_priority_scope_flag",
    "access_recency_sort_key",
]

SILENT_ID_FIELDS = {
    "snapshot_ds",
    "merchant_country_code",
    "merchant_id",
    "institution_id",
    "mcc_code",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build reviewed private data package for ANZ BI Streamlit.")
    parser.add_argument("--output-root", required=True, help="Target projects/anz-bi-platform directory.")
    parser.add_argument("--new-intake-prepared", default=str(DEFAULT_NEW_INTAKE_PREPARED))
    parser.add_argument("--activation-prepared", default=str(DEFAULT_ACTIVATION_PREPARED))
    parser.add_argument("--silent-detail", default=str(DEFAULT_SILENT_DETAIL))
    parser.add_argument("--silent-aggregate", default=str(DEFAULT_SILENT_AGGREGATE))
    parser.add_argument(
        "--silent-only",
        action="store_true",
        help="Update only processed/silent_merchants and its manifest entry.",
    )
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()

    output_root = Path(args.output_root).expanduser()
    new_intake_prepared = Path(args.new_intake_prepared).expanduser()
    activation_prepared = Path(args.activation_prepared).expanduser()
    silent_detail = Path(args.silent_detail).expanduser()
    silent_aggregate = Path(args.silent_aggregate).expanduser()

    if args.silent_only:
        payload = _write_silent_page_slice(
            output_root=output_root,
            silent_detail=silent_detail,
            silent_aggregate=silent_aggregate,
            version=args.version,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    _require_file(new_intake_prepared / "new_intake_rows.json")
    _require_file(new_intake_prepared / "new_intake_summary.json")
    _require_file(new_intake_prepared / "new_intake_institution_rollup.json")
    _require_file(activation_prepared / "merchant_distribution_points.json")
    _require_file(activation_prepared / "low_activity_bi_summary.json")
    _require_file(activation_prepared / "area_low_activity_rollup.json")
    _require_file(silent_detail)
    _require_file(silent_aggregate)

    new_intake_rows = _load_list(new_intake_prepared / "new_intake_rows.json")
    activation_rows = _load_list(activation_prepared / "merchant_distribution_points.json")
    new_intake_summary = _load_dict(new_intake_prepared / "new_intake_summary.json")
    silent_raw = _load_table(silent_detail)
    silent_aggregate_table = _normalize_text_frame(_load_table(silent_aggregate))

    processed = output_root / "processed"
    new_intake_out = processed / "new_intake"
    activation_out = processed / "activation_low_activity"
    silent_out = processed / "silent_merchants"
    shared_out = processed / "shared_dimensions"

    output_root.mkdir(parents=True, exist_ok=True)
    new_intake_out.mkdir(parents=True, exist_ok=True)
    activation_out.mkdir(parents=True, exist_ok=True)
    silent_out.mkdir(parents=True, exist_ok=True)
    shared_out.mkdir(parents=True, exist_ok=True)

    new_intake_table = pd.DataFrame([_pick(row, NEW_INTAKE_FIELDS) for row in new_intake_rows])
    activation_table = pd.DataFrame([_activation_row(row) for row in activation_rows])
    silent_table = _silent_rows(silent_raw)
    new_intake_table = with_reporting_geography(
        new_intake_table,
        country_columns=["analysis_country", "country_group", "merchant_country_code"],
    )
    activation_table = with_reporting_geography(
        activation_table,
        country_columns=["scope_country", "country_group", "merchant_country_code"],
    )
    silent_table = with_reporting_geography(
        silent_table,
        country_columns=["country_group", "merchant_country_code"],
    )
    geo_bridge = geo_reporting_bridge_contract()

    _write_dataframe_csv(new_intake_out / "new_intake_rows.csv", new_intake_table)
    _write_dataframe_csv(activation_out / "activation_candidates.csv", activation_table)
    _write_dataframe_csv(silent_out / "silent_merchants_rows.csv", silent_table)
    _write_dataframe_csv(silent_out / "silent_merchants_aggregate.csv", silent_aggregate_table)
    _write_dataframe_csv(shared_out / "geo_reporting_bridge.csv", geo_bridge)
    _write_rollup_json_as_csv(
        new_intake_prepared / "new_intake_institution_rollup.json",
        new_intake_out / "new_intake_institution_rollup.csv",
    )
    _write_rollup_json_as_csv(
        activation_prepared / "area_low_activity_rollup.json",
        activation_out / "area_low_activity_rollup.csv",
        item_key="items",
    )

    shutil.copy2(new_intake_prepared / "new_intake_summary.json", new_intake_out / "new_intake_summary.json")
    shutil.copy2(activation_prepared / "low_activity_bi_summary.json", activation_out / "low_activity_bi_summary.json")

    new_intake_provider = new_intake_provider_export(new_intake_table)
    new_intake_internal = new_intake_internal_export(new_intake_table)
    activation_provider = activation_provider_export(activation_table)
    activation_internal = activation_internal_export(activation_table)
    silent_provider = silent_merchants_provider_export(silent_table)
    silent_internal = silent_merchants_internal_export(silent_table)

    _write_dataframe_csv(new_intake_out / "new_intake_provider_export.csv", new_intake_provider)
    _write_dataframe_csv(new_intake_out / "new_intake_internal_record_export.csv", new_intake_internal)
    _write_dataframe_csv(new_intake_out / "new_intake_export.csv", new_intake_provider)
    _write_dataframe_csv(activation_out / "activation_provider_export.csv", activation_provider)
    _write_dataframe_csv(activation_out / "activation_internal_record_export.csv", activation_internal)
    _write_dataframe_csv(activation_out / "activation_export.csv", activation_provider)
    _write_dataframe_csv(silent_out / "silent_merchants_provider_export.csv", silent_provider)
    _write_dataframe_csv(silent_out / "silent_merchants_internal_record_export.csv", silent_internal)
    _write_dataframe_csv(silent_out / "silent_merchants_export.csv", silent_provider)

    silent_summary = _silent_summary(
        rows=silent_table,
        aggregate=silent_aggregate_table,
        detail_source=silent_detail,
        aggregate_source=silent_aggregate,
    )
    (silent_out / "silent_merchants_summary.json").write_text(
        json.dumps(silent_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "project_id": PROJECT_ID,
        "version": args.version,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contract": {
            "dataset_layout": "page_scoped",
            "page_root": "processed/<page_id>/",
            "shared_root": "processed/shared_dimensions/",
            "geo_project": "anz-geography",
            "page_update_rule": (
                "Each BI page owns its processed/<page_id>/ directory and manifest page_datasets entry. "
                "Refreshing one page should not require rewriting unrelated page directories."
            ),
        },
        "source": {
            "new_intake_prepared": str(new_intake_prepared),
            "activation_prepared": str(activation_prepared),
            "silent_detail": str(silent_detail),
            "silent_aggregate": str(silent_aggregate),
            "geo_project": "anz-geography",
        },
        "page_datasets": {
            "new_intake": {
                "schema_version": SCHEMA_VERSION,
                "export_contract_version": EXPORT_CONTRACT_VERSION,
                "page_root": "processed/new_intake/",
                "privacy_level": "aggregate_plus_desensitized_merchant_detail",
                "source_period": _new_intake_source_period(new_intake_summary),
                "row_count": len(new_intake_rows),
                "files": {
                    "rows": "processed/new_intake/new_intake_rows.csv",
                    "summary": "processed/new_intake/new_intake_summary.json",
                    "institution_rollup": "processed/new_intake/new_intake_institution_rollup.csv",
                    "export": "processed/new_intake/new_intake_export.csv",
                    "provider_export": "processed/new_intake/new_intake_provider_export.csv",
                    "internal_record_export": "processed/new_intake/new_intake_internal_record_export.csv",
                },
            },
            "activation_low_activity": {
                "schema_version": SCHEMA_VERSION,
                "export_contract_version": EXPORT_CONTRACT_VERSION,
                "page_root": "processed/activation_low_activity/",
                "privacy_level": "aggregate_plus_desensitized_merchant_detail",
                "source_period": "prev_3m_candidate_pool",
                "row_count": len(activation_rows),
                "files": {
                    "rows": "processed/activation_low_activity/activation_candidates.csv",
                    "summary": "processed/activation_low_activity/low_activity_bi_summary.json",
                    "area_rollup": "processed/activation_low_activity/area_low_activity_rollup.csv",
                    "export": "processed/activation_low_activity/activation_export.csv",
                    "provider_export": "processed/activation_low_activity/activation_provider_export.csv",
                    "internal_record_export": "processed/activation_low_activity/activation_internal_record_export.csv",
                },
            },
            "silent_merchants": {
                "schema_version": SCHEMA_VERSION,
                "export_contract_version": EXPORT_CONTRACT_VERSION,
                "page_root": "processed/silent_merchants/",
                "privacy_level": "aggregate_plus_desensitized_merchant_detail",
                "source_period": "2023-01-01 to 2026-05-01; snapshot 20260501",
                "row_count": len(silent_table),
                "aggregate_merchant_count": silent_summary["aggregate_merchant_count"],
                "files": {
                    "rows": "processed/silent_merchants/silent_merchants_rows.csv",
                    "summary": "processed/silent_merchants/silent_merchants_summary.json",
                    "aggregate": "processed/silent_merchants/silent_merchants_aggregate.csv",
                    "export": "processed/silent_merchants/silent_merchants_export.csv",
                    "provider_export": "processed/silent_merchants/silent_merchants_provider_export.csv",
                    "internal_record_export": "processed/silent_merchants/silent_merchants_internal_record_export.csv",
                },
            },
        },
        "shared_dimensions": {
            "geo_reporting_bridge": {
                "schema_version": GEO_CONTRACT_VERSION,
                "privacy_level": "non_sensitive_contract",
                "row_count": len(geo_bridge),
                "files": {
                    "bridge": "processed/shared_dimensions/geo_reporting_bridge.csv",
                },
            },
        },
        "guardrails": [
            "No raw exports, Excel workbooks, SQLite databases, local secrets, contact, bank, legal representative, director, shareholder, UBO, or certificate fields.",
            "Provider exports exclude merchant_id, institution_id, candidate_rank, and other internal identifiers.",
            "Internal record exports include merchant_id and institution_id for system lookup and must remain inside Tencent/internal handling.",
            "New Intake txn_count_30d and txn_amount_30d mean first 30 days after onboarding, not market-wide rolling 30 days.",
            "Activation is region-first; coordinates are optional and not required for the first Streamlit release.",
            "Silent Merchants excludes ONLINE and Zhenxing records, requires access age >= 180 days, and keeps only merchants with zero latest-180-day transactions.",
            "AU and NZ do not share the same business geography hierarchy. Streamlit uses geo_reporting_level/name as the shared interface and keeps NZ geo_area/cluster country-specific.",
        ],
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"output_root": str(output_root), "manifest": manifest}, ensure_ascii=False, indent=2))
    return 0


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def _write_silent_page_slice(
    *,
    output_root: Path,
    silent_detail: Path,
    silent_aggregate: Path,
    version: str,
) -> dict[str, Any]:
    _require_file(silent_detail)
    _require_file(silent_aggregate)

    silent_raw = _load_table(silent_detail)
    silent_aggregate_table = _normalize_text_frame(_load_table(silent_aggregate))
    silent_table = _silent_rows(silent_raw)
    silent_table = with_reporting_geography(
        silent_table,
        country_columns=["country_group", "merchant_country_code"],
    )
    silent_provider = silent_merchants_provider_export(silent_table)
    silent_internal = silent_merchants_internal_export(silent_table)
    silent_summary = _silent_summary(
        rows=silent_table,
        aggregate=silent_aggregate_table,
        detail_source=silent_detail,
        aggregate_source=silent_aggregate,
    )

    silent_out = output_root / "processed" / "silent_merchants"
    silent_out.mkdir(parents=True, exist_ok=True)
    _write_dataframe_csv(silent_out / "silent_merchants_rows.csv", silent_table)
    _write_dataframe_csv(silent_out / "silent_merchants_aggregate.csv", silent_aggregate_table)
    _write_dataframe_csv(silent_out / "silent_merchants_provider_export.csv", silent_provider)
    _write_dataframe_csv(silent_out / "silent_merchants_internal_record_export.csv", silent_internal)
    _write_dataframe_csv(silent_out / "silent_merchants_export.csv", silent_provider)
    (silent_out / "silent_merchants_summary.json").write_text(
        json.dumps(silent_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = _load_or_create_manifest(output_root)
    manifest["version"] = version
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest.setdefault("source", {})
    manifest["source"]["silent_detail"] = str(silent_detail)
    manifest["source"]["silent_aggregate"] = str(silent_aggregate)
    manifest.setdefault("page_datasets", {})
    manifest["page_datasets"]["silent_merchants"] = _silent_manifest_entry(silent_summary, len(silent_table))
    manifest.setdefault("guardrails", [])
    _append_unique(
        manifest["guardrails"],
        "Silent Merchants excludes ONLINE and Zhenxing records, requires access age >= 180 days, and keeps only merchants with zero latest-180-day transactions.",
    )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output_root": str(output_root), "manifest": manifest}


def _load_or_create_manifest(output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "manifest.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict):
            return payload
    return {
        "project_id": PROJECT_ID,
        "contract": {
            "dataset_layout": "page_scoped",
            "page_root": "processed/<page_id>/",
            "shared_root": "processed/shared_dimensions/",
            "geo_project": "anz-geography",
            "page_update_rule": (
                "Each BI page owns its processed/<page_id>/ directory and manifest page_datasets entry. "
                "Refreshing one page should not require rewriting unrelated page directories."
            ),
        },
        "source": {"geo_project": "anz-geography"},
        "page_datasets": {},
        "shared_dimensions": {},
        "guardrails": [],
    }


def _silent_manifest_entry(summary: dict[str, Any], row_count: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "export_contract_version": EXPORT_CONTRACT_VERSION,
        "page_root": "processed/silent_merchants/",
        "privacy_level": "aggregate_plus_desensitized_merchant_detail",
        "source_period": summary["source_period"],
        "row_count": row_count,
        "aggregate_merchant_count": summary["aggregate_merchant_count"],
        "files": {
            "rows": "processed/silent_merchants/silent_merchants_rows.csv",
            "summary": "processed/silent_merchants/silent_merchants_summary.json",
            "aggregate": "processed/silent_merchants/silent_merchants_aggregate.csv",
            "export": "processed/silent_merchants/silent_merchants_export.csv",
            "provider_export": "processed/silent_merchants/silent_merchants_provider_export.csv",
            "internal_record_export": "processed/silent_merchants/silent_merchants_internal_record_export.csv",
        },
    }


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str).fillna("")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=str).fillna("")
    raise ValueError(f"Unsupported table format for {path}; expected .csv, .xlsx, or .xls")


def _load_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON array: {path}")
    return [row for row in payload if isinstance(row, dict)]


def _load_dict(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _pick(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {field: row.get(field, "") for field in fields}


def _activation_row(row: dict[str, Any]) -> dict[str, Any]:
    item = _pick(row, ACTIVATION_FIELDS)
    band = str(item.get("decay_band") or "")
    item["priority_label"] = ACTIVATION_PRIORITY_LABELS.get(band, band)
    return item


def _silent_rows(df: pd.DataFrame) -> pd.DataFrame:
    normalized = _normalize_text_frame(df)
    out = _select_frame_columns(normalized, SILENT_FIELDS)
    if "address" not in out.columns or out["address"].fillna("").astype(str).str.strip().eq("").all():
        out["address"] = out["stores_address"] if "stores_address" in out.columns else ""
    out = _cast_string_columns(out, SILENT_ID_FIELDS)
    return out


def _select_frame_columns(df: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    payload: dict[str, Any] = {}
    for field in fields:
        if field in df.columns:
            payload[field] = df[field]
        else:
            payload[field] = pd.Series([""] * len(df), index=df.index)
    return pd.DataFrame(payload, index=df.index)[fields]


def _normalize_text_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(column).strip() for column in out.columns]
    for column in out.columns:
        if pd.api.types.is_object_dtype(out[column]) or pd.api.types.is_string_dtype(out[column]):
            out[column] = out[column].fillna("").astype(str).str.replace("\u00a0", " ", regex=False).str.strip()
    return out.fillna("")


def _cast_string_columns(df: pd.DataFrame, columns: set[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = out[column].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    return out


def _silent_summary(
    *,
    rows: pd.DataFrame,
    aggregate: pd.DataFrame,
    detail_source: Path,
    aggregate_source: Path,
) -> dict[str, Any]:
    aggregate_count = _aggregate_merchant_count(aggregate)
    return {
        "page_id": "silent_merchants",
        "schema_version": SCHEMA_VERSION,
        "export_contract_version": EXPORT_CONTRACT_VERSION,
        "source_period": "2023-01-01 to 2026-05-01; snapshot 20260501",
        "snapshot_ds": _first_nonempty(rows, "snapshot_ds") or "20260501",
        "detail_row_count": len(rows),
        "aggregate_merchant_count": aggregate_count,
        "detail_source": str(detail_source),
        "aggregate_source": str(aggregate_source),
        "business_definition": {
            "countries": ["AU", "NZ"],
            "business_type": ["OFFLINE", "BOTH"],
            "exclude_online": True,
            "exclude_zhenxing": True,
            "minimum_access_age_days": 180,
            "silent_signal": "txn_count_180d = 0",
        },
        "tier_distribution": _counts(rows, "silence_tier"),
        "country_distribution": _counts(rows, "country_group"),
        "aggregate_tier_distribution": _aggregate_counts(aggregate, "silent_category"),
        "aggregate_country_distribution": _aggregate_counts(aggregate, "country_group"),
    }


def _aggregate_merchant_count(df: pd.DataFrame) -> int:
    if "merchant_count" not in df.columns:
        return 0
    return int(pd.to_numeric(df["merchant_count"], errors="coerce").fillna(0).sum())


def _aggregate_counts(df: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in df.columns or "merchant_count" not in df.columns:
        return {}
    working = df.copy()
    working["merchant_count"] = pd.to_numeric(working["merchant_count"], errors="coerce").fillna(0)
    grouped = working.groupby(column, dropna=False)["merchant_count"].sum().sort_values(ascending=False)
    return {str(key): int(value) for key, value in grouped.to_dict().items()}


def _counts(df: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in df.columns:
        return {}
    return {str(key): int(value) for key, value in df[column].fillna("").astype(str).value_counts().to_dict().items()}


def _first_nonempty(df: pd.DataFrame, column: str) -> str:
    if column not in df.columns:
        return ""
    values = df[column].fillna("").astype(str).str.strip()
    values = values[values != ""]
    return values.iloc[0] if not values.empty else ""


def _write_rollup_json_as_csv(path: Path, output_path: Path, *, item_key: str | None = None) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if item_key:
        rows = payload.get(item_key, []) if isinstance(payload, dict) else []
    else:
        rows = payload
    if not isinstance(rows, list):
        rows = []
    fieldnames: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    _write_csv(output_path, (row for row in rows if isinstance(row, dict)), fieldnames)


def _write_csv(path: Path, rows: Any, fieldnames: list[str]) -> int:
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def _write_dataframe_csv(path: Path, df: pd.DataFrame) -> int:
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return len(df)


def _new_intake_source_period(summary: dict[str, Any]) -> str:
    months = sorted((summary.get("month_distribution") or {}).keys())
    if not months:
        return "unknown"
    return f"{months[0]} to {months[-1]}"


if __name__ == "__main__":
    raise SystemExit(main())
