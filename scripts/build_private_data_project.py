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
    "severe": "优先铺设",
    "high": "重点铺设",
    "medium": "机会铺设",
    "stable": "维护经营",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build reviewed private data package for ANZ BI Streamlit.")
    parser.add_argument("--output-root", required=True, help="Target projects/anz-bi-platform directory.")
    parser.add_argument("--new-intake-prepared", default=str(DEFAULT_NEW_INTAKE_PREPARED))
    parser.add_argument("--activation-prepared", default=str(DEFAULT_ACTIVATION_PREPARED))
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()

    output_root = Path(args.output_root).expanduser()
    new_intake_prepared = Path(args.new_intake_prepared).expanduser()
    activation_prepared = Path(args.activation_prepared).expanduser()

    _require_file(new_intake_prepared / "new_intake_rows.json")
    _require_file(new_intake_prepared / "new_intake_summary.json")
    _require_file(new_intake_prepared / "new_intake_institution_rollup.json")
    _require_file(activation_prepared / "merchant_distribution_points.json")
    _require_file(activation_prepared / "low_activity_bi_summary.json")
    _require_file(activation_prepared / "area_low_activity_rollup.json")

    new_intake_rows = _load_list(new_intake_prepared / "new_intake_rows.json")
    activation_rows = _load_list(activation_prepared / "merchant_distribution_points.json")
    new_intake_summary = _load_dict(new_intake_prepared / "new_intake_summary.json")

    processed = output_root / "processed"
    new_intake_out = processed / "new_intake"
    activation_out = processed / "activation_low_activity"
    shared_out = processed / "shared_dimensions"

    output_root.mkdir(parents=True, exist_ok=True)
    new_intake_out.mkdir(parents=True, exist_ok=True)
    activation_out.mkdir(parents=True, exist_ok=True)
    shared_out.mkdir(parents=True, exist_ok=True)

    new_intake_table = pd.DataFrame([_pick(row, NEW_INTAKE_FIELDS) for row in new_intake_rows])
    activation_table = pd.DataFrame([_activation_row(row) for row in activation_rows])
    new_intake_table = with_reporting_geography(
        new_intake_table,
        country_columns=["analysis_country", "country_group", "merchant_country_code"],
    )
    activation_table = with_reporting_geography(
        activation_table,
        country_columns=["scope_country", "country_group", "merchant_country_code"],
    )
    geo_bridge = geo_reporting_bridge_contract()

    _write_dataframe_csv(new_intake_out / "new_intake_rows.csv", new_intake_table)
    _write_dataframe_csv(activation_out / "activation_candidates.csv", activation_table)
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

    _write_dataframe_csv(new_intake_out / "new_intake_provider_export.csv", new_intake_provider)
    _write_dataframe_csv(new_intake_out / "new_intake_internal_record_export.csv", new_intake_internal)
    _write_dataframe_csv(new_intake_out / "new_intake_export.csv", new_intake_provider)
    _write_dataframe_csv(activation_out / "activation_provider_export.csv", activation_provider)
    _write_dataframe_csv(activation_out / "activation_internal_record_export.csv", activation_internal)
    _write_dataframe_csv(activation_out / "activation_export.csv", activation_provider)

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
            "AU and NZ do not share the same business geography hierarchy. Streamlit uses geo_reporting_level/name as the shared interface and keeps NZ geo_area/cluster country-specific.",
        ],
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"output_root": str(output_root), "manifest": manifest}, ensure_ascii=False, indent=2))
    return 0


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


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
