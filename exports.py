from __future__ import annotations

from typing import Any

import pandas as pd

from geography import with_reporting_geography


NEW_INTAKE_PROVIDER_COLUMNS = [
    "intake_month",
    "商家名",
    "机构",
    "国家",
    "州/省",
    "所在城市",
    "Suburb",
    "Postcode",
    "地理展示层级",
    "地理展示名称",
    "NZ地理片区",
    "NZ Cluster",
    "接入后30天激活状态",
    "详细地址",
    "行业",
]

NEW_INTAKE_INTERNAL_COLUMNS = [
    "merchant_id",
    "institution_id",
    "intake_month",
    "merchant_company_name",
    "merchant_short_name",
    "institution_name",
    "institution_standard",
    "analysis_country",
    "geo_country",
    "geo_state",
    "geo_city",
    "geo_suburb",
    "geo_postcode",
    "geo_reporting_level",
    "geo_reporting_level_label",
    "geo_reporting_name",
    "nz_geo_area",
    "nz_business_cluster",
    "au_service_area",
    "business_city",
    "business_suburb",
    "geo_area",
    "business_cluster",
    "business_area",
    "channel_type",
    "mcc_code",
    "mcc_major_industry",
    "active_30d_flag",
    "txn_count_30d",
    "txn_amount_30d",
    "is_zhenxing",
    "store_address",
]

ACTIVATION_PROVIDER_COLUMNS = [
    "商家名",
    "国家",
    "州/省",
    "所在城市",
    "Suburb",
    "Postcode",
    "地理展示层级",
    "地理展示名称",
    "NZ地理片区",
    "NZ Cluster",
    "铺设优先级",
    "详细地址",
    "行业",
]

ACTIVATION_INTERNAL_COLUMNS = [
    "merchant_id",
    "institution_id",
    "merchant_name",
    "merchant_short_name",
    "institution_name",
    "institution_group",
    "scope_country",
    "geo_country",
    "geo_state",
    "geo_city",
    "geo_suburb",
    "geo_postcode",
    "geo_reporting_level",
    "geo_reporting_level_label",
    "geo_reporting_name",
    "nz_geo_area",
    "nz_business_cluster",
    "au_service_area",
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
    "decay_band",
    "priority_label",
    "candidate_rank",
    "address",
]


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def new_intake_provider_export(rows: pd.DataFrame) -> pd.DataFrame:
    rows = with_reporting_geography(
        rows,
        country_columns=["analysis_country", "country_group", "merchant_country_code"],
    )
    payload = pd.DataFrame(
        {
            "intake_month": _col(rows, "intake_month"),
            "商家名": _first_text(rows, ["merchant_short_name", "merchant_company_name"]),
            "机构": _first_text(rows, ["institution_standard", "institution_name"]),
            "国家": _col(rows, "geo_country"),
            "州/省": _col(rows, "geo_state"),
            "所在城市": _col(rows, "geo_city"),
            "Suburb": _col(rows, "geo_suburb"),
            "Postcode": _col(rows, "geo_postcode"),
            "地理展示层级": _col(rows, "geo_reporting_level_label"),
            "地理展示名称": _col(rows, "geo_reporting_name"),
            "NZ地理片区": _col(rows, "nz_geo_area"),
            "NZ Cluster": _col(rows, "nz_business_cluster"),
            "接入后30天激活状态": _active_label(_col(rows, "active_30d_flag")),
            "详细地址": _col(rows, "store_address"),
            "行业": _first_text(rows, ["mcc_major_industry", "mcc_code"]),
        }
    )
    return payload[NEW_INTAKE_PROVIDER_COLUMNS]


def new_intake_internal_export(rows: pd.DataFrame) -> pd.DataFrame:
    rows = with_reporting_geography(
        rows,
        country_columns=["analysis_country", "country_group", "merchant_country_code"],
    )
    return _select_existing(rows, NEW_INTAKE_INTERNAL_COLUMNS)


def activation_provider_export(rows: pd.DataFrame) -> pd.DataFrame:
    rows = with_reporting_geography(
        rows,
        country_columns=["scope_country", "country_group", "merchant_country_code"],
    )
    payload = pd.DataFrame(
        {
            "商家名": _first_text(rows, ["merchant_name", "merchant_short_name"]),
            "国家": _col(rows, "geo_country"),
            "州/省": _col(rows, "geo_state"),
            "所在城市": _col(rows, "geo_city"),
            "Suburb": _col(rows, "geo_suburb"),
            "Postcode": _col(rows, "geo_postcode"),
            "地理展示层级": _col(rows, "geo_reporting_level_label"),
            "地理展示名称": _col(rows, "geo_reporting_name"),
            "NZ地理片区": _col(rows, "nz_geo_area"),
            "NZ Cluster": _col(rows, "nz_business_cluster"),
            "铺设优先级": _first_text(rows, ["priority_label", "decay_band"]),
            "详细地址": _first_text(rows, ["address", "normalized_address"]),
            "行业": _first_text(rows, ["mcc_major_industry", "mcc_industry", "mcc_name", "mcc"]),
        }
    )
    return payload[ACTIVATION_PROVIDER_COLUMNS]


def activation_internal_export(rows: pd.DataFrame) -> pd.DataFrame:
    rows = with_reporting_geography(
        rows,
        country_columns=["scope_country", "country_group", "merchant_country_code"],
    )
    return _select_existing(rows, ACTIVATION_INTERNAL_COLUMNS)


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    if name in df.columns:
        return df[name].fillna("")
    return pd.Series([""] * len(df), index=df.index)


def _first_text(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series([""] * len(df), index=df.index, dtype=object)
    for column in columns:
        values = _col(df, column).astype(str)
        result = result.where(result.astype(str).str.strip() != "", values)
    return result.fillna("")


def _active_label(values: pd.Series) -> pd.Series:
    return values.astype(str).map(lambda value: "已激活" if value in {"1", "1.0", "true", "True"} else "未激活")


def _select_existing(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    payload: dict[str, Any] = {}
    for column in columns:
        payload[column] = _col(df, column)
    return pd.DataFrame(payload, index=df.index)[columns]
