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

