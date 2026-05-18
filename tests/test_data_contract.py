from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from charts import combo_line_bar_option, donut_option, horizontal_bar_option
from data_loader import DataLoadError, validate_project
from exports import (
    activation_internal_export,
    activation_provider_export,
    new_intake_internal_export,
    new_intake_provider_export,
)
from geo_matching import StreamlitGeoMatcher, append_staging_geo_columns
from geography import country_scope, sidebar_geo_filter_specs, with_reporting_geography
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
                "priority_label": "优先铺设",
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
    assert "merchant_id" in internal.columns
    assert "candidate_rank" in internal.columns


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
