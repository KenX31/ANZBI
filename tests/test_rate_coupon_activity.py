from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_loader import DataLoadError, validate_project  # noqa: E402
from pages_or_modules.rate_coupon_activity import (  # noqa: E402
    METRIC_OPTIONS,
    filter_month_range,
    issued_redeemed_trend_option,
    latest_month,
    monthly_trend,
    month_options,
    stacked_stock_option,
    stock_name_option_map,
    stock_totals,
    summary_metrics,
)
from scripts.materialize_rate_coupon_activity import (  # noqa: E402
    PAGE_ID,
    SCHEMA_VERSION,
    build_rate_coupon_monthly,
    write_rate_coupon_activity_slice,
)
from ui_labels import PAGE_LABELS  # noqa: E402


def test_rate_coupon_materializer_writes_page_slice(tmp_path: Path) -> None:
    source = tmp_path / "rate_coupon_monthly.csv"
    _raw_frame().to_csv(source, index=False, encoding="utf-8-sig")
    output_root = tmp_path / "anz-bi-platform"
    output_root.mkdir()
    (output_root / "manifest.json").write_text(
        json.dumps(
            {
                "project_id": "anz-bi-platform",
                "version": "baseline",
                "page_datasets": {"new_intake": {"schema_version": "1.0"}},
                "guardrails": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = write_rate_coupon_activity_slice(
        output_root=output_root,
        source_monthly=source,
        version="test-rate-coupon",
        generated_at="2026-05-19T00:00:00+00:00",
    )

    page_root = output_root / "processed" / PAGE_ID
    monthly = pd.read_parquet(page_root / "rate_coupon_monthly.parquet").astype(str)
    metadata = pd.read_parquet(page_root / "rate_coupon_stock_metadata.parquet").astype(str)
    summary = json.loads((page_root / "rate_coupon_summary.json").read_text(encoding="utf-8-sig"))
    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8-sig"))

    assert result["page_id"] == PAGE_ID
    assert manifest["page_datasets"][PAGE_ID]["schema_version"] == SCHEMA_VERSION
    assert manifest["page_datasets"][PAGE_ID]["storage_format"] == "parquet"
    assert manifest["page_datasets"]["new_intake"]["schema_version"] == "1.0"
    assert manifest["source"]["rate_coupon_activity_monthly"] == str(source)
    assert monthly["stock_id"].tolist() == [
        "stv2-1742544739781708",
        "stv2-1742544739781708",
        "stv2-1761807586025667",
    ]
    assert metadata["stock_key"].tolist() == ["nz_food_industry", "au_food_industry"]
    assert summary["latest_month"] == "2026-01"
    assert summary["totals"]["redeemed_coupon_code_count_trade"] == 19.0
    assert "raw order" in manifest["guardrails"][-1]
    assert result["files"]["monthly"].endswith(".parquet")


def test_rate_coupon_materializer_normalizes_internal_contract(tmp_path: Path) -> None:
    monthly = build_rate_coupon_monthly(_fixture_path(tmp_path))

    assert "stockid" not in monthly.columns
    assert monthly["country_group"].tolist() == ["NZ", "NZ", "AU"]
    assert monthly["stock_key"].tolist() == ["nz_food_industry", "nz_food_industry", "au_food_industry"]
    assert monthly["month_order"].tolist() == [202503, 202504, 202601]
    assert pd.to_numeric(monthly["redemption_gap_count"]).tolist() == [0, 1, 0]


def test_rate_coupon_page_helpers_sort_filter_and_summarize(tmp_path: Path) -> None:
    rows = build_rate_coupon_monthly(_fixture_path(tmp_path))

    assert month_options(rows) == ["2025-03", "2025-04", "2026-01"]
    assert latest_month(rows) == "2026-01"

    filtered = filter_month_range(rows, "2025-04", "2026-01")
    metrics = summary_metrics(filtered)
    totals = stock_totals(filtered)

    assert filtered["month_label"].tolist() == ["2025-04", "2026-01"]
    assert metrics["stock_count"] == 2
    assert metrics["latest_active_merchants"] == 2
    assert metrics["latest_redeemed_coupons"] == 4
    assert totals["stock_id"].tolist() == ["stv2-1742544739781708", "stv2-1761807586025667"]


def test_rate_coupon_stock_name_options_map_to_stock_ids(tmp_path: Path) -> None:
    rows = build_rate_coupon_monthly(_fixture_path(tmp_path))
    options = stock_name_option_map(rows)

    assert list(options.values()) == [["stv2-1742544739781708"], ["stv2-1761807586025667"]]
    assert all("(stv2-" not in label for label in options)


def test_rate_coupon_page_uses_english_internal_keys(tmp_path: Path) -> None:
    assert list(PAGE_LABELS) == [
        "new_intake",
        "activation_low_activity",
        "rate_coupon_activity",
        "silent_merchants",
    ]
    assert all(key.isascii() for key in PAGE_LABELS)
    assert all(option.isascii() for option in METRIC_OPTIONS)
    assert METRIC_OPTIONS[0] == "issued_coupon_code_count"

    rows = build_rate_coupon_monthly(_fixture_path(tmp_path))
    option = stacked_stock_option(rows, metric="redeeming_submerchant_count", title="demo")

    assert option["series"][0]["name"] == "新西兰-餐饮行业汇率"
    assert option["series"][0]["type"] == "bar"
    assert option["legend"]["bottom"] == 0

    trend_option = issued_redeemed_trend_option(monthly_trend(rows), title="demo")
    assert [series["name"] for series in trend_option["series"]] == [
        "领券数量",
        "核销券码数",
        "核销率",
    ]
    assert trend_option["series"][2]["yAxisIndex"] == 1


def test_manifest_schema_guard_requires_rate_coupon_activity() -> None:
    try:
        validate_project(
            {
                "manifest": {
                    "project_id": "anz-bi-platform",
                    "page_datasets": {
                        "new_intake": {"schema_version": "1.0"},
                        "activation_low_activity": {"schema_version": "1.0"},
                        "silent_merchants": {"schema_version": "1.0"},
                    },
                }
            }
        )
    except DataLoadError as exc:
        assert "rate_coupon_activity schema version" in str(exc)
    else:
        raise AssertionError("validate_project should require the rate coupon activity dataset")


def _fixture_path(tmp_path: Path) -> Path:
    path = tmp_path / "rate_coupon_fixture.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    _raw_frame().to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "month_label": "2025-03",
                "stockid": "stv2-1742544739781708",
                "stock_name_cn": "新西兰-餐饮行业汇率",
                "month_first_ds": "20250321",
                "month_last_ds": "20250331",
                "issued_coupon_code_count": "8",
                "used_coupon_code_count_stock_dim": "1",
                "redeemed_coupon_code_count_trade": "1",
                "redeeming_submerchant_count": "1",
                "trade_order_count": "1",
                "trade_row_count": "1",
                "pay_amt_cny_yuan": "100",
                "user_save_money_yuan": "10",
                "cost_money_yuan": "2",
            },
            {
                "month_label": "2025-04",
                "stockid": "stv2-1742544739781708",
                "stock_name_cn": "新西兰-餐饮行业汇率",
                "month_first_ds": "20250401",
                "month_last_ds": "20250430",
                "issued_coupon_code_count": "20",
                "used_coupon_code_count_stock_dim": "15",
                "redeemed_coupon_code_count_trade": "14",
                "redeeming_submerchant_count": "3",
                "trade_order_count": "14",
                "trade_row_count": "14",
                "pay_amt_cny_yuan": "200",
                "user_save_money_yuan": "20",
                "cost_money_yuan": "4",
            },
            {
                "month_label": "2026-01",
                "stockid": "stv2-1761807586025667",
                "stock_name_cn": "澳洲-餐饮行业汇率",
                "month_first_ds": "20260101",
                "month_last_ds": "20260131",
                "issued_coupon_code_count": "7",
                "used_coupon_code_count_stock_dim": "4",
                "redeemed_coupon_code_count_trade": "4",
                "redeeming_submerchant_count": "2",
                "trade_order_count": "4",
                "trade_row_count": "4",
                "pay_amt_cny_yuan": "300",
                "user_save_money_yuan": "30",
                "cost_money_yuan": "-1",
            },
        ]
    )
