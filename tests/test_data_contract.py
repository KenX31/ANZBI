from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from charts import combo_line_bar_option, donut_option, horizontal_bar_option
from charts import combo_bar_count_line_option
from data_loader import DataLoadError, _normalize_amount_units, _read_csv_text, validate_project
from exports import (
    activation_internal_export,
    activation_provider_export,
    new_intake_internal_export,
    new_intake_provider_export,
)
from geo_matching import StreamlitGeoMatcher, append_staging_geo_columns
from geography import country_scope, sidebar_geo_filter_specs, with_reporting_geography
from pages_or_modules.new_intake import (
    ONLINE_SCOPE_EXCLUDE,
    _apply_online_scope,
    _apply_zhenxing_scope,
    _default_month_range,
    _filter_month_range,
    _latest_month,
    _month_options,
)
from pages_or_modules.activation_low_activity import (
    _activity_windows,
    _classify_frequency_decline,
    _with_frequency_decline_band,
)
from scripts.build_private_data_project import _new_intake_source_period


def test_manifest_schema_guard_accepts_expected_versions() -> None:
    validate_project(
        {
            "manifest": {
                "project_id": "anz-bi-platform",
                "page_datasets": {
                    "new_intake": {"schema_version": "1.0"},
                    "activation_low_activity": {"schema_version": "1.0"},
                },
            }
        }
    )


def test_manifest_schema_guard_rejects_stale_versions() -> None:
    try:
        validate_project(
            {
                "manifest": {
                    "project_id": "anz-bi-platform",
                    "page_datasets": {
                        "new_intake": {"schema_version": "0.9"},
                        "activation_low_activity": {"schema_version": "1.0"},
                    },
                }
            }
        )
    except DataLoadError as exc:
        assert "new_intake schema version" in str(exc)
    else:
        raise AssertionError("validate_project should reject stale schema versions")


def test_new_intake_source_period_uses_month_distribution() -> None:
    assert _new_intake_source_period({"month_distribution": {"2026.03": 1, "2022.01": 1}}) == "2022.01 to 2026.03"


def test_new_intake_provider_export_excludes_internal_ids() -> None:
    rows = pd.DataFrame(
        [
            {
                "merchant_id": "456",
                "institution_id": "psp1",
                "intake_month": "2026.03",
                "merchant_short_name": "Demo Shop",
                "institution_standard": "Demo PSP",
                "analysis_country": "NZ",
                "business_city": "Auckland",
                "geo_area": "Auckland Central",
                "business_cluster": "CBD",
                "active_30d_flag": 1,
                "store_address": "Demo address",
                "mcc_major_industry": "餐饮类",
            }
        ]
    )
    provider = new_intake_provider_export(rows)
    internal = new_intake_internal_export(rows)
    assert "merchant_id" not in provider.columns
    assert "institution_id" not in provider.columns
    assert "merchant_id" in internal.columns
    assert internal.loc[0, "merchant_id"] == "456"
    assert provider.loc[0, "接入后30天激活状态"] == "已激活"
    assert provider.loc[0, "地理展示名称"] == "Auckland Central"


def test_activation_provider_export_excludes_internal_ids() -> None:
    rows = pd.DataFrame(
        [
            {
                "merchant_id": "123",
                "institution_id": "psp2",
                "candidate_rank": 8,
                "merchant_name": "Demo Merchant",
                "business_city": "Auckland",
                "priority_label": "严重下滑",
                "address": "Demo address",
                "mcc_major_industry": "餐饮类",
            }
        ]
    )
    provider = activation_provider_export(rows)
    internal = activation_internal_export(rows)
    assert "merchant_id" not in provider.columns
    assert "institution_id" not in provider.columns
    assert "candidate_rank" not in provider.columns
    assert "服务商跟进级别" in provider.columns
    assert "merchant_id" in internal.columns
    assert "candidate_rank" in internal.columns


def test_amount_columns_are_scaled_from_minor_units() -> None:
    rows = pd.DataFrame(
        [
            {
                "txn_amount_30d": 12345,
                "trade_amt_prev_1m": 250,
                "txn_count_30d": 7,
                "merchant_id": "m1",
            }
        ]
    )

    normalized = _normalize_amount_units(rows, "minor")

    assert normalized.loc[0, "txn_amount_30d"] == 123.45
    assert normalized.loc[0, "trade_amt_prev_1m"] == 2.5
    assert normalized.loc[0, "txn_count_30d"] == 7
    assert normalized.loc[0, "merchant_id"] == "m1"


def test_csv_reader_preserves_intake_month_labels() -> None:
    rows = _read_csv_text("intake_month,txn_amount_30d\n2025.10,100\n")
    assert rows.loc[0, "intake_month"] == "2025.10"


def test_new_intake_default_month_range_uses_latest_six_calendar_months() -> None:
    rows = pd.DataFrame(
        {
            "intake_month": [
                "2025.08",
                "2025.09",
                "2025.10",
                "2025.11",
                "2025.12",
                "2026.01",
                "2026.02",
                "2026.03",
            ],
            "merchant_id": list(range(8)),
        }
    )

    months = _month_options(rows)
    assert _default_month_range(months) == ("2025.10", "2026.03")
    assert _latest_month(rows) == "2026.03"

    filtered = _filter_month_range(rows, "2025.10", "2026.03")
    assert filtered["intake_month"].tolist() == ["2025.10", "2025.11", "2025.12", "2026.01", "2026.02", "2026.03"]


def test_new_intake_month_options_recover_legacy_october_label() -> None:
    rows = pd.DataFrame(
        {
            "intake_month": ["2025.09", "2025.1", "2025.11", "2025.12", "2026.01", "2026.02", "2026.03"],
            "merchant_id": list(range(7)),
        }
    )

    months = _month_options(rows)
    assert "2025.10" in months
    assert "2025.1" not in months
    assert _default_month_range(months) == ("2025.10", "2026.03")

    filtered = _filter_month_range(rows, "2025.10", "2026.03")
    assert filtered["intake_month"].tolist() == ["2025.1", "2025.11", "2025.12", "2026.01", "2026.02", "2026.03"]


def test_new_intake_default_scope_excludes_online_and_zhenxing() -> None:
    rows = pd.DataFrame(
        {
            "merchant_id": ["offline", "online", "zhenxing"],
            "channel_type": ["OFFLINE", "ONLINE", "BOTH"],
            "is_zhenxing": ["0", "0", "1"],
        }
    )

    scoped = _apply_zhenxing_scope(_apply_online_scope(rows, ONLINE_SCOPE_EXCLUDE), "排除圳兴")

    assert scoped["merchant_id"].tolist() == ["offline"]


def test_activation_monitoring_uses_q1_frequency_decline_bands() -> None:
    rows = pd.DataFrame(
        [
            {"merchant_id": "stable", "trade_cnt_prev_3m": 100, "trade_cnt_prev_2m": 100, "trade_cnt_prev_1m": 80},
            {"merchant_id": "medium", "trade_cnt_prev_3m": 100, "trade_cnt_prev_2m": 100, "trade_cnt_prev_1m": 60},
            {"merchant_id": "high", "trade_cnt_prev_3m": 100, "trade_cnt_prev_2m": 100, "trade_cnt_prev_1m": 20},
            {"merchant_id": "severe", "trade_cnt_prev_3m": 100, "trade_cnt_prev_2m": 100, "trade_cnt_prev_1m": 0},
        ]
    )

    monitored = _with_frequency_decline_band(rows)

    assert monitored["decay_band"].tolist() == ["stable", "medium", "high", "severe"]
    assert monitored["eligible_low_activity_flag"].tolist() == [True, True, True, True]
    assert _classify_frequency_decline(jan=0, feb=100, mar=0) == ("stable", 0.0)


def test_activation_activity_windows_are_q1_frequency_in_calendar_order() -> None:
    rows = pd.DataFrame(
        [
            {"trade_cnt_prev_1m": 10, "trade_cnt_prev_2m": 20, "trade_cnt_prev_3m": 30},
            {"trade_cnt_prev_1m": 1, "trade_cnt_prev_2m": 2, "trade_cnt_prev_3m": 3},
        ]
    )

    windows = _activity_windows(rows)

    assert windows["window"].tolist() == ["2026.1", "2026.2", "2026.3"]
    assert windows["txn_count"].tolist() == [33, 22, 11]
    assert windows["active_merchant_count"].tolist() == [2, 2, 2]


def test_activation_combo_chart_uses_bar_and_line_axes() -> None:
    rows = pd.DataFrame(
        [
            {"window": "2026.1", "txn_count": 230008, "active_merchant_count": 5000},
            {"window": "2026.2", "txn_count": 275000, "active_merchant_count": 4259},
        ]
    )

    option = combo_bar_count_line_option(
        rows,
        x="window",
        bar_y="txn_count",
        line_y="active_merchant_count",
        title="2026 Q1",
        bar_name="交易频次",
        line_name="活跃商户数",
    )

    assert option["series"][0]["type"] == "bar"
    assert option["series"][1]["type"] == "line"
    assert option["series"][1]["yAxisIndex"] == 1


def test_reporting_geography_keeps_country_specific_levels() -> None:
    rows = pd.DataFrame(
        [
            {
                "analysis_country": "NZ",
                "business_city": "Auckland",
                "business_suburb": "Albany",
                "geo_area": "North Shore",
                "business_cluster": "Albany Cluster",
                "staging_city": "Auckland",
                "staging_geo_area": "Central Auckland",
                "staging_business_cluster": "Reviewed Cluster",
            },
            {
                "analysis_country": "AU",
                "state": "NSW",
                "business_city": "Sydney",
                "business_suburb": "Haymarket",
                "staging_city": "Sydney",
                "geo_area": "Should not be AU geo area",
                "business_cluster": "Should not be AU cluster",
            },
            {
                "analysis_country": "NZ",
                "business_city": "Auckland",
                "geo_area": "Legacy Auckland Area",
                "staging_city": "",
                "staging_geo_area": "",
            },
        ]
    )

    bridged = with_reporting_geography(rows, country_columns="analysis_country")

    assert bridged.loc[0, "geo_reporting_level"] == "nz_geo_area"
    assert bridged.loc[0, "geo_reporting_name"] == "Central Auckland"
    assert bridged.loc[0, "nz_business_cluster"] == "Reviewed Cluster"
    assert bridged.loc[1, "geo_reporting_level"] == "au_city"
    assert bridged.loc[1, "geo_reporting_name"] == "Sydney"
    assert bridged.loc[1, "nz_geo_area"] == ""
    assert bridged.loc[1, "nz_business_cluster"] == ""
    assert bridged.loc[2, "nz_geo_area"] == ""
    assert bridged.loc[2, "geo_city"] == ""
    assert country_scope(bridged.iloc[[0]]) == "NZ"
    assert [spec.column for spec in sidebar_geo_filter_specs("AU")] == [
        "geo_state",
        "geo_city",
        "geo_suburb",
        "geo_postcode",
    ]


def test_geo_matcher_can_use_private_repo_frames() -> None:
    rows = pd.DataFrame(
        [
            {
                "analysis_country": "NZ",
                "merchant_short_name": "Demo",
                "store_address": "1 Queen Street, Auckland 1010",
            }
        ]
    )
    matcher = StreamlitGeoMatcher.from_frames(
        nz=pd.DataFrame(
            [
                {
                    "Country": "NZ",
                    "City": "Auckland",
                    "geo_area": "Central Auckland",
                    "Suburb": "Auckland Central",
                    "Postcode": "1010",
                    "business_cluster": "CBD",
                }
            ]
        ),
        au=pd.DataFrame([{"Country": "AU", "State": "NSW", "City": "Sydney", "Suburb": "Haymarket", "Postcode": "2000"}]),
    )
    staged = append_staging_geo_columns(rows, matcher)
    assert staged.loc[0, "staging_geo_area"] == "Central Auckland"
    assert staged.loc[0, "staging_business_cluster"] == "CBD"


def test_echarts_option_builders_return_core_shapes() -> None:
    trend = pd.DataFrame([{"month": "2026.03", "count": 10, "rate": 0.4}])
    combo = combo_line_bar_option(
        trend,
        x="month",
        bar_y="count",
        line_y="rate",
        title="Trend",
        bar_name="Count",
        line_name="Rate",
    )
    assert combo["series"][0]["type"] == "bar"
    assert combo["series"][1]["type"] == "line"

    dist = pd.DataFrame([{"label": "NZ", "count": 3}])
    donut = donut_option(dist, label="label", value="count", title="Country")
    assert donut["series"][0]["type"] == "pie"

    rank = horizontal_bar_option(dist, label="label", value="count", title="Rank")
    assert rank["series"][0]["type"] == "bar"
