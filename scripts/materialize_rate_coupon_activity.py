from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PAGE_ID = "rate_coupon_activity"
SCHEMA_VERSION = "1.0"
STORAGE_FORMAT = "parquet"
DEFAULT_VERSION = "2026.05.19-rate-coupon-v1"
DEFAULT_SOURCE_MONTHLY = Path(
    r"D:\Tencent\Data analysis\2026.5.15_NZ_rate_coupon_stock_monthly\data\raw\rate_coupon_stock_from_start_to_202604_monthly.csv"
)

STOCK_CONTRACT = [
    {
        "stock_id": "stv2-1736755174536325",
        "stock_key": "nz_queenstown_area",
        "stock_name_cn": "新西兰-皇后镇商圈汇率",
        "country_group": "NZ",
        "stock_sort_order": 10,
    },
    {
        "stock_id": "stv2-1742544739781708",
        "stock_key": "nz_food_industry",
        "stock_name_cn": "新西兰-餐饮行业汇率",
        "country_group": "NZ",
        "stock_sort_order": 20,
    },
    {
        "stock_id": "stv2-1749805132612063",
        "stock_key": "nz_north_island",
        "stock_name_cn": "新西兰-北岛汇率",
        "country_group": "NZ",
        "stock_sort_order": 30,
    },
    {
        "stock_id": "stv2-1774957378147285",
        "stock_key": "nz_south_island",
        "stock_name_cn": "新西兰-南岛汇率",
        "country_group": "NZ",
        "stock_sort_order": 40,
    },
    {
        "stock_id": "stv2-1743513165300441",
        "stock_key": "au_chinatown",
        "stock_name_cn": "澳洲-唐人街活动汇率",
        "country_group": "AU",
        "stock_sort_order": 50,
    },
    {
        "stock_id": "stv2-1761807586025667",
        "stock_key": "au_food_industry",
        "stock_name_cn": "澳洲-餐饮行业汇率",
        "country_group": "AU",
        "stock_sort_order": 60,
    },
]

NUMERIC_COLUMNS = [
    "month_first_ds",
    "month_last_ds",
    "issued_coupon_code_count",
    "used_coupon_code_count_stock_dim",
    "redeemed_coupon_code_count_trade",
    "redeeming_submerchant_count",
    "trade_order_count",
    "trade_row_count",
    "pay_amt_cny_yuan",
    "user_save_money_yuan",
    "cost_money_yuan",
]

OUTPUT_MONTHLY_COLUMNS = [
    "month_label",
    "month_order",
    "stock_id",
    "stock_key",
    "stock_name_cn",
    "stock_label",
    "country_group",
    "stock_sort_order",
    "month_first_ds",
    "month_last_ds",
    "issued_coupon_code_count",
    "used_coupon_code_count_stock_dim",
    "redeemed_coupon_code_count_trade",
    "redeeming_submerchant_count",
    "trade_order_count",
    "trade_row_count",
    "pay_amt_cny_yuan",
    "user_save_money_yuan",
    "cost_money_yuan",
    "redemption_gap_count",
    "redeemed_per_active_merchant",
    "cost_per_redeemed_coupon_yuan",
]

OUTPUT_METADATA_COLUMNS = [
    "stock_id",
    "stock_key",
    "stock_name_cn",
    "stock_label",
    "country_group",
    "stock_sort_order",
    "first_month",
    "latest_month",
    "month_count",
    "total_issued_coupon_code_count",
    "total_used_coupon_code_count_stock_dim",
    "total_redeemed_coupon_code_count_trade",
    "active_merchant_month_sum",
    "total_trade_order_count",
    "total_pay_amt_cny_yuan",
    "total_user_save_money_yuan",
    "total_cost_money_yuan",
    "max_monthly_redeeming_submerchant_count",
]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = write_rate_coupon_activity_slice(
        output_root=args.output_root,
        source_monthly=args.source_monthly,
        version=args.version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize the rate coupon activity BI page data slice.")
    parser.add_argument("--output-root", type=Path, required=True, help="Target projects/anz-bi-platform directory.")
    parser.add_argument("--source-monthly", type=Path, default=DEFAULT_SOURCE_MONTHLY)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    return parser.parse_args(argv)


def write_rate_coupon_activity_slice(
    *,
    output_root: Path,
    source_monthly: Path,
    version: str = DEFAULT_VERSION,
    generated_at: str | None = None,
) -> dict[str, Any]:
    monthly = build_rate_coupon_monthly(source_monthly)
    metadata = build_stock_metadata(monthly)
    summary = build_summary(
        monthly=monthly,
        metadata=metadata,
        source_monthly=source_monthly,
    )

    page_root = output_root / "processed" / PAGE_ID
    page_root.mkdir(parents=True, exist_ok=True)
    monthly.to_parquet(page_root / "rate_coupon_monthly.parquet", index=False)
    metadata.to_parquet(page_root / "rate_coupon_stock_metadata.parquet", index=False)
    (page_root / "rate_coupon_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = _load_or_create_manifest(output_root)
    manifest["version"] = version
    manifest["generated_at"] = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest.setdefault("contract", {})["storage_format"] = STORAGE_FORMAT
    manifest.setdefault("source", {})
    manifest["source"]["rate_coupon_activity_monthly"] = str(source_monthly)
    manifest.setdefault("page_datasets", {})
    manifest["page_datasets"][PAGE_ID] = {
        "schema_version": SCHEMA_VERSION,
        "storage_format": STORAGE_FORMAT,
        "page_root": f"processed/{PAGE_ID}/",
        "privacy_level": "aggregate_monthly_activity",
        "source_period": summary["source_period"],
        "row_count": int(len(monthly)),
        "stock_count": int(metadata["stock_id"].nunique()) if not metadata.empty else 0,
        "files": {
            "monthly": f"processed/{PAGE_ID}/rate_coupon_monthly.parquet",
            "stock_metadata": f"processed/{PAGE_ID}/rate_coupon_stock_metadata.parquet",
            "summary": f"processed/{PAGE_ID}/rate_coupon_summary.json",
        },
    }
    manifest.setdefault("guardrails", [])
    _append_unique(
        manifest["guardrails"],
        "Rate coupon activity stores only monthly stock-level aggregates; no raw order, coupon, user, contact, bank, legal, shareholder, director, or UBO fields.",
    )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "output_root": str(output_root),
        "page_id": PAGE_ID,
        "version": version,
        "row_count": int(len(monthly)),
        "stock_count": int(metadata["stock_id"].nunique()) if not metadata.empty else 0,
        "latest_month": summary["latest_month"],
        "files": manifest["page_datasets"][PAGE_ID]["files"],
    }


def build_rate_coupon_monthly(source_monthly: Path) -> pd.DataFrame:
    if not source_monthly.exists():
        raise FileNotFoundError(source_monthly)

    raw = pd.read_csv(source_monthly, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = {"month_label", "stockid", "stock_name_cn"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns in {source_monthly}: {sorted(missing)}")

    stock_contract = pd.DataFrame(STOCK_CONTRACT)
    out = raw.rename(columns={"stockid": "stock_id"}).copy()
    out = out[out["stock_id"].isin(stock_contract["stock_id"])].copy()
    out = out.merge(
        stock_contract.drop(columns=["stock_name_cn"]),
        how="left",
        on="stock_id",
        validate="many_to_one",
    )
    out["stock_name_cn"] = out["stock_name_cn"].where(
        out["stock_name_cn"].astype(str).str.strip() != "",
        out["stock_id"].map(dict(zip(stock_contract["stock_id"], stock_contract["stock_name_cn"], strict=False))),
    )
    out["stock_label"] = out["stock_name_cn"].fillna("").astype(str).str.strip()
    out.loc[out["stock_label"] == "", "stock_label"] = out["stock_id"]
    out["month_order"] = out["month_label"].map(month_order_key)

    for column in NUMERIC_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
        else:
            out[column] = 0

    out["redemption_gap_count"] = out["used_coupon_code_count_stock_dim"] - out["redeemed_coupon_code_count_trade"]
    out["redeemed_per_active_merchant"] = _safe_divide(
        out["redeemed_coupon_code_count_trade"],
        out["redeeming_submerchant_count"],
    )
    out["cost_per_redeemed_coupon_yuan"] = _safe_divide(
        out["cost_money_yuan"],
        out["redeemed_coupon_code_count_trade"],
    )
    out["stock_sort_order"] = pd.to_numeric(out["stock_sort_order"], errors="coerce").fillna(999).astype(int)
    out = out.sort_values(["month_order", "stock_sort_order", "stock_id"], kind="stable")
    return out[OUTPUT_MONTHLY_COLUMNS].reset_index(drop=True)


def build_stock_metadata(monthly: pd.DataFrame) -> pd.DataFrame:
    if monthly.empty:
        return pd.DataFrame(columns=OUTPUT_METADATA_COLUMNS)

    grouped = monthly.groupby(
        ["stock_id", "stock_key", "stock_name_cn", "stock_label", "country_group", "stock_sort_order"],
        dropna=False,
    ).agg(
        first_month=("month_label", _first_month),
        latest_month=("month_label", _latest_month),
        month_count=("month_label", "nunique"),
        total_issued_coupon_code_count=("issued_coupon_code_count", "sum"),
        total_used_coupon_code_count_stock_dim=("used_coupon_code_count_stock_dim", "sum"),
        total_redeemed_coupon_code_count_trade=("redeemed_coupon_code_count_trade", "sum"),
        active_merchant_month_sum=("redeeming_submerchant_count", "sum"),
        total_trade_order_count=("trade_order_count", "sum"),
        total_pay_amt_cny_yuan=("pay_amt_cny_yuan", "sum"),
        total_user_save_money_yuan=("user_save_money_yuan", "sum"),
        total_cost_money_yuan=("cost_money_yuan", "sum"),
        max_monthly_redeeming_submerchant_count=("redeeming_submerchant_count", "max"),
    )
    out = grouped.reset_index().sort_values(["stock_sort_order", "stock_id"], kind="stable")
    return out[OUTPUT_METADATA_COLUMNS]


def build_summary(*, monthly: pd.DataFrame, metadata: pd.DataFrame, source_monthly: Path) -> dict[str, Any]:
    first_month = _first_month(monthly["month_label"]) if not monthly.empty else ""
    latest_month = _latest_month(monthly["month_label"]) if not monthly.empty else ""
    return {
        "page_id": PAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "source_file": str(source_monthly),
        "source_period": f"{first_month} to {latest_month}" if first_month and latest_month else "unknown",
        "first_month": first_month,
        "latest_month": latest_month,
        "row_count": int(len(monthly)),
        "stock_count": int(metadata["stock_id"].nunique()) if not metadata.empty else 0,
        "month_count": int(monthly["month_label"].nunique()) if not monthly.empty else 0,
        "countries": sorted(monthly["country_group"].dropna().astype(str).unique().tolist()) if not monthly.empty else [],
        "metric_definitions": {
            "active_merchant_count": "Monthly stock-level sum of redeeming_submerchant_count, defined as distinct sub_mchid with coupon redemption in the month and stock batch.",
            "redeemed_coupon_count": "Monthly stock-level redeemed_coupon_code_count_trade, defined as count(distinct coupon_code) from the trade/funds table.",
            "stock_dimension_used_coupon_count": "Monthly delta of current_use_coupon_code_count from the stock dimension, kept as a cross-check.",
            "cost_money_yuan": "Monthly stock-level cost_money_yuan from the trade/funds table; negative values are preserved as source data.",
        },
        "totals": {
            "issued_coupon_code_count": _sum(monthly, "issued_coupon_code_count"),
            "used_coupon_code_count_stock_dim": _sum(monthly, "used_coupon_code_count_stock_dim"),
            "redeemed_coupon_code_count_trade": _sum(monthly, "redeemed_coupon_code_count_trade"),
            "active_merchant_month_sum": _sum(monthly, "redeeming_submerchant_count"),
            "trade_order_count": _sum(monthly, "trade_order_count"),
            "pay_amt_cny_yuan": round(_sum(monthly, "pay_amt_cny_yuan"), 2),
            "user_save_money_yuan": round(_sum(monthly, "user_save_money_yuan"), 2),
            "cost_money_yuan": round(_sum(monthly, "cost_money_yuan"), 2),
        },
    }


def month_order_key(value: object) -> int:
    text = str(value or "").strip().replace("/", "-").replace(".", "-")
    parts = text.split("-")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        year = int(parts[0])
        month = int(parts[1])
        if 1 <= month <= 12:
            return year * 100 + month
    return 999999


def _first_month(values: pd.Series) -> str:
    months = sorted((str(value) for value in values if str(value).strip()), key=month_order_key)
    return months[0] if months else ""


def _latest_month(values: pd.Series) -> str:
    months = sorted((str(value) for value in values if str(value).strip()), key=month_order_key)
    return months[-1] if months else ""


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    top = pd.to_numeric(numerator, errors="coerce").fillna(0)
    bottom = pd.to_numeric(denominator, errors="coerce").fillna(0)
    return top.divide(bottom.mask(bottom.eq(0))).fillna(0).round(4)


def _sum(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _load_or_create_manifest(output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "manifest.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict):
            return payload
    return {
        "project_id": "anz-bi-platform",
        "contract": {
            "dataset_layout": "page_scoped",
            "storage_format": STORAGE_FORMAT,
            "page_root": "processed/<page_id>/",
            "shared_root": "processed/shared_dimensions/",
            "geo_project": "anz-geography",
            "page_update_rule": (
                "Each BI page owns its processed/<page_id>/ directory and manifest page_datasets entry. "
                "Refreshing one page should not require rewriting unrelated page directories."
            ),
        },
        "source": {},
        "page_datasets": {},
        "shared_dimensions": {},
        "guardrails": [],
    }


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


if __name__ == "__main__":
    raise SystemExit(main())
