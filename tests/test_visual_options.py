from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from charts import donut_option, treemap_option
from pages_or_modules.activation_low_activity import _industry_decline_treemap
from pages_or_modules.new_intake import _industry_activation_treemap


def test_donut_labels_are_always_visible() -> None:
    option = donut_option(
        pd.DataFrame([{"label": "NZ", "count": 3}, {"label": "AU", "count": 2}]),
        label="label",
        value="count",
        title="国家分布",
    )

    label = option["series"][0]["label"]
    assert label["show"] is True
    assert "{d}%" in label["formatter"]


def test_treemap_labels_show_share_and_rate() -> None:
    option = treemap_option(
        pd.DataFrame(
            [
                {"label": "餐饮", "merchant_count": 75, "active_30d_rate": 0.4},
                {"label": "零售", "merchant_count": 25, "active_30d_rate": 0.8},
            ]
        ),
        label="label",
        value="merchant_count",
        title="行业分布",
        color_by="active_30d_rate",
        color_name="30天激活率",
    )

    data = option["series"][0]["data"]
    assert data[0]["label"]["formatter"] == "餐饮\n占比 75.0%\n30天激活率 40.0%"
    assert data[0]["itemStyle"]["color"].startswith("#")


def test_new_intake_industry_treemap_uses_activation_rate() -> None:
    rows = pd.DataFrame(
        [
            {"merchant_id": "a", "mcc_major_industry": "餐饮", "active_30d_flag": 1},
            {"merchant_id": "b", "mcc_major_industry": "餐饮", "active_30d_flag": 0},
            {"merchant_id": "c", "mcc_major_industry": "零售", "active_30d_flag": 1},
        ]
    )

    grouped = _industry_activation_treemap(rows)
    food = grouped[grouped["label"] == "餐饮"].iloc[0]

    assert food["merchant_count"] == 2
    assert food["active_30d_rate"] == 0.5


def test_activation_industry_treemap_uses_decline_rate() -> None:
    rows = pd.DataFrame(
        [
            {"merchant_id": "a", "mcc_major_industry": "餐饮", "eligible_low_activity_flag": True, "decay_band": "high"},
            {"merchant_id": "b", "mcc_major_industry": "餐饮", "eligible_low_activity_flag": True, "decay_band": "stable"},
            {"merchant_id": "c", "mcc_major_industry": "零售", "eligible_low_activity_flag": True, "decay_band": "severe"},
        ]
    )

    grouped = _industry_decline_treemap(rows)
    food = grouped[grouped["label"] == "餐饮"].iloc[0]

    assert food["merchant_count"] == 2
    assert food["low_activity_ratio"] == 0.5
