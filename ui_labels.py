from __future__ import annotations

import pandas as pd


COUNTRY_LABELS = {
    "AU": "澳大利亚",
    "NZ": "新西兰",
}

CHANNEL_LABELS = {
    "BOTH": "线上+线下",
    "OFFLINE": "线下",
    "ONLINE": "线上",
}

ACTIVE_30D_LABELS = {
    "0": "未激活",
    "0.0": "未激活",
    "1": "已激活",
    "1.0": "已激活",
}

DECAY_BAND_LABELS = {
    "high": "明显下滑",
    "medium": "稍微下滑",
    "severe": "严重下滑",
    "stable": "稳定",
}

WINDOW_LABELS = {
    "prev_3m": "2026.1",
    "prev_2m": "2026.2",
    "prev_1m": "2026.3",
}

COLUMN_LABELS = {
    "active_30d_count": "接入后30天激活商户数",
    "active_30d_flag": "接入后30天激活",
    "active_30d_rate": "接入后30天激活率",
    "address": "地址",
    "candidate_rank": "候选排名",
    "channel_type": "渠道",
    "decay_band": "活跃等级",
    "eligible_count": "可评估商户数",
    "eligible_low_activity_flag": "可评估标记",
    "geo_city": "城市",
    "geo_country": "国家",
    "geo_postcode": "邮编",
    "geo_reporting_level": "地理层级代码",
    "geo_reporting_level_label": "地理层级",
    "geo_reporting_name": "地理展示名称",
    "geo_state": "州/省",
    "geo_suburb": "街区",
    "institution_name": "机构名称",
    "institution_standard": "机构标准名",
    "intake_month": "进件月份",
    "low_activity_count": "下滑商户数",
    "low_activity_ratio": "下滑占比",
    "mcc_major_industry": "行业",
    "merchant_count": "商户数",
    "merchant_id": "商户MID",
    "merchant_name": "商户名称",
    "merchant_short_name": "商户简称",
    "nz_business_cluster": "NZ 商圈集群",
    "nz_geo_area": "NZ 地理片区",
    "priority_label": "服务商跟进级别",
    "scope_country": "国家",
    "severe_count": "严重下滑商户数",
    "trade_cnt_prev_3m": "2026.1交易笔数",
    "trade_cnt_prev_2m": "2026.2交易笔数",
    "trade_cnt_prev_1m": "2026.3交易笔数",
    "trade_amt_prev_3m": "2026.1交易金额",
    "trade_amt_prev_2m": "2026.2交易金额",
    "trade_amt_prev_1m": "2026.3交易金额",
    "txn_amount_30d": "接入后30天交易金额",
    "txn_count": "交易笔数",
    "txn_count_30d": "接入后30天交易笔数",
    "window": "交易窗口",
}


def display_table(df: pd.DataFrame) -> pd.DataFrame:
    out = apply_value_labels(df)
    return out.rename(columns={key: value for key, value in COLUMN_LABELS.items() if key in out.columns})


def apply_value_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    _map_column(out, "active_30d_flag", ACTIVE_30D_LABELS)
    _map_column(out, "analysis_country", COUNTRY_LABELS)
    _map_column(out, "channel_type", CHANNEL_LABELS)
    _map_column(out, "decay_band", DECAY_BAND_LABELS)
    _map_column(out, "geo_country", COUNTRY_LABELS)
    _map_column(out, "scope_country", COUNTRY_LABELS)
    _map_column(out, "window", WINDOW_LABELS)
    return out


def label_value(value: object, mapping: dict[str, str]) -> str:
    text = str(value or "").strip()
    if text.casefold() in {"", "nan", "none", "null", "unknown"}:
        return "未分类"
    return mapping.get(text, text or "未分类")


def _map_column(df: pd.DataFrame, column: str, mapping: dict[str, str]) -> None:
    if column in df.columns:
        df[column] = df[column].map(lambda value: label_value(value, mapping))
