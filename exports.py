from __future__ import annotations

from typing import Any

import pandas as pd

from geography import with_reporting_geography


NEW_INTAKE_PROVIDER_COLUMNS = [
    "商家名",
    "所在城市",
    "Suburb",
    "州/省",
    "Postcode",
    "NZ地理片区",
    "接入后30天激活状态",
    "intake_month",
    "详细地址",
    "行业展示",
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
    "geo_reporting_name",
    "nz_geo_area",
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
    "所在城市",
    "NZ地理片区",
    "Suburb",
    "详细地址",
    "行业",
    "铺设优先级",
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

SILENT_PROVIDER_COLUMNS = [
    "商家名",
    "所在城市",
    "NZ地理片区",
    "Suburb",
    "详细地址",
    "行业",
    "铺设优先级",
]

SILENT_INTERNAL_COLUMNS = [
    "merchant_id",
    "institution_id",
    "merchant_display_name",
    "merchant_company_name",
    "merchant_short_name",
    "institution_name",
    "institution_group",
    "snapshot_ds",
    "country_group",
    "merchant_country_code",
    "geo_country",
    "geo_state",
    "geo_city",
    "geo_suburb",
    "geo_postcode",
    "geo_reporting_name",
    "nz_geo_area",
    "nz_business_cluster",
    "au_service_area",
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

SILENT_TIER_LABELS = {
    "new_unactivated_180d": "新接入180天未激活",
    "initial_silent": "初始沉默",
    "deep_silent": "深度沉默",
}

SILENT_ACCESS_AGE_LABELS = {
    "access_180_359d": "接入180-359天",
    "access_gte_360d": "接入360天及以上",
}

SILENT_BUSINESS_TYPE_LABELS = {
    "BOTH": "线上+线下",
    "OFFLINE": "线下",
    "ONLINE": "线上",
}

SILENT_COUNTRY_LABELS = {
    "AU": "澳大利亚",
    "NZ": "新西兰",
}

SERVICE_PROVIDER_PRIORITY_LABELS = {
    "severe": "优先铺设",
    "严重下滑": "优先铺设",
    "new_unactivated_180d": "优先铺设",
    "新接入180天未激活": "优先铺设",
    "high": "重点铺设",
    "明显下滑": "重点铺设",
    "initial_silent": "重点铺设",
    "初始沉默": "重点铺设",
    "medium": "机会铺设",
    "稍微下滑": "机会铺设",
    "deep_silent": "机会铺设",
    "深度沉默": "机会铺设",
    "stable": "",
    "稳定": "",
}


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
            "州/省": _col(rows, "geo_state"),
            "所在城市": _col(rows, "geo_city"),
            "Suburb": _col(rows, "geo_suburb"),
            "Postcode": _col(rows, "geo_postcode"),
            "NZ地理片区": _col(rows, "nz_geo_area"),
            "接入后30天激活状态": _active_label(_col(rows, "active_30d_flag")),
            "详细地址": _col(rows, "store_address"),
            "行业展示": _first_text(rows, ["mcc_major_industry", "mcc_code"]),
        }
    )
    return _select_nonempty(payload, NEW_INTAKE_PROVIDER_COLUMNS)


def new_intake_internal_export(rows: pd.DataFrame) -> pd.DataFrame:
    rows = with_reporting_geography(
        rows,
        country_columns=["analysis_country", "country_group", "merchant_country_code"],
    )
    return _select_existing(rows, NEW_INTAKE_INTERNAL_COLUMNS, drop_empty=True)


def activation_provider_export(rows: pd.DataFrame) -> pd.DataFrame:
    rows = with_reporting_geography(
        rows,
        country_columns=["scope_country", "country_group", "merchant_country_code"],
    )
    payload = pd.DataFrame(
        {
            "商家名": _first_text(rows, ["merchant_name", "merchant_short_name"]),
            "所在城市": _col(rows, "geo_city"),
            "NZ地理片区": _col(rows, "nz_geo_area"),
            "Suburb": _col(rows, "geo_suburb"),
            "详细地址": _first_text(rows, ["address", "normalized_address"]),
            "行业": _first_text(rows, ["mcc_major_industry", "mcc_industry", "mcc_name", "mcc"]),
            "铺设优先级": _service_provider_priority(_first_text(rows, ["priority_label", "decay_band"])),
        }
    )
    return payload[ACTIVATION_PROVIDER_COLUMNS]


def activation_internal_export(rows: pd.DataFrame) -> pd.DataFrame:
    rows = with_reporting_geography(
        rows,
        country_columns=["scope_country", "country_group", "merchant_country_code"],
    )
    return _select_existing(rows, ACTIVATION_INTERNAL_COLUMNS, drop_empty=True)


def silent_merchants_provider_export(rows: pd.DataFrame) -> pd.DataFrame:
    rows = with_reporting_geography(
        rows,
        country_columns=["country_group", "merchant_country_code"],
    )
    payload = pd.DataFrame(
        {
            "商家名": _first_text(rows, ["merchant_display_name", "merchant_short_name", "merchant_company_name"]),
            "所在城市": _col(rows, "geo_city"),
            "NZ地理片区": _col(rows, "nz_geo_area"),
            "Suburb": _col(rows, "geo_suburb"),
            "详细地址": _first_text(rows, ["address", "stores_address"]),
            "行业": _first_text(rows, ["mcc_major_industry", "mcc_industry", "mcc_name", "mcc", "mcc_code"]),
            "铺设优先级": _service_provider_priority(_col(rows, "silence_tier")),
        }
    )
    return payload[SILENT_PROVIDER_COLUMNS]


def silent_merchants_internal_export(rows: pd.DataFrame) -> pd.DataFrame:
    rows = with_reporting_geography(
        rows,
        country_columns=["country_group", "merchant_country_code"],
    )
    return _select_existing(rows, SILENT_INTERNAL_COLUMNS, drop_empty=True)


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


def _map_values(values: pd.Series, mapping: dict[str, str]) -> pd.Series:
    return values.astype(str).map(lambda value: mapping.get(value, value))


def _service_provider_priority(values: pd.Series) -> pd.Series:
    return _map_values(values, SERVICE_PROVIDER_PRIORITY_LABELS)


def _select_existing(df: pd.DataFrame, columns: list[str], *, drop_empty: bool = False) -> pd.DataFrame:
    payload: dict[str, Any] = {}
    for column in columns:
        payload[column] = _col(df, column)
    frame = pd.DataFrame(payload, index=df.index)[columns]
    if drop_empty:
        return frame[_nonempty_columns(frame, columns)]
    return frame


def _select_nonempty(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frame = df[columns]
    return frame[_nonempty_columns(frame, columns)]


def _nonempty_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    if df.empty:
        return columns
    return [column for column in columns if not _is_blank_series(df[column])]


def _is_blank_series(values: pd.Series) -> bool:
    text = values.fillna("").astype(str).str.strip()
    return bool(text.eq("").all())
