from __future__ import annotations

import pandas as pd
import streamlit as st

from charts import (
    PALETTE,
    SEVERITY_COLORS,
    donut_option,
    horizontal_bar_option,
    render_echart,
    simple_bar_option,
    treemap_option,
)
from exports import activation_internal_export, activation_provider_export, csv_bytes
from filters import apply_text_filter, disabled_multiselect_filter, mapped_multiselect_filter, multiselect_filter, options
from geography import country_scope, sidebar_geo_filter_specs, with_reporting_geography
from metrics import format_int, format_pct, rate, sum_number
from ui_labels import COUNTRY_LABELS, DECAY_BAND_LABELS, WINDOW_LABELS, display_table, label_value


LOW_ACTIVITY_BANDS = {"severe", "high", "medium"}
PRIORITY_LABELS = {
    "severe": "严重下滑",
    "high": "明显下滑",
    "medium": "稍微下滑",
    "stable": "稳定",
}
SEVERITY_DISPLAY_COLORS = {
    label_value(key, DECAY_BAND_LABELS): value for key, value in SEVERITY_COLORS.items()
}


def render_activation_page(data: dict[str, object]) -> None:
    rows = with_reporting_geography(
        data["rows"].copy(),  # type: ignore[index, union-attr]
        country_columns=["scope_country", "country_group", "merchant_country_code"],
    )
    if rows.empty:
        st.warning("没有可用的活跃监测数据。")
        return

    st.header("活跃监测")
    st.caption(
        "当前口径：按 2026 Q1 商户交易频次做活跃监测；以 2026.1 有交易作为可评估基础，"
        "再观察 2026.3 相对 2026.2 的交易频次是否下滑。后续按季度更新数据，下一次周期为 "
        "2026.04.01-2026.06.30。"
    )
    st.info(
        "等级解释：严重下滑表示 2026.2 仍有交易、但 2026.3 已经为 0；明显下滑表示 2026.3 交易频次相对 "
        "2026.2 降到 35% 以下；稍微下滑表示 2026.3 交易频次相对 2026.2 降到 70% 以下；"
        "稳定表示仍在活跃、暂时未落入低活跃规则。"
        "这些等级用于生成服务商跟进清单。"
    )

    rows = _with_frequency_decline_band(_normalize_numeric(rows))
    filtered = _with_priority_label(_sidebar_filters(rows))
    eligible = int(sum_number(filtered, "eligible_low_activity_flag"))
    low_activity = int(filtered["decay_band"].astype(str).isin(LOW_ACTIVITY_BANDS).sum()) if "decay_band" in filtered else 0
    severe = int((filtered["decay_band"].astype(str) == "severe").sum()) if "decay_band" in filtered else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("候选商户", format_int(len(filtered)))
    c2.metric("可评估", format_int(eligible))
    c3.metric("下滑占比", format_pct(rate(low_activity, eligible)))
    c4.metric("严重下滑", format_int(severe))

    if filtered.empty:
        st.info("当前筛选下没有匹配商户。")
        return

    provider_export = activation_provider_export(filtered)
    internal_export = activation_internal_export(filtered)
    d1, d2 = st.columns(2)
    d1.download_button(
        "导出服务商执行清单",
        csv_bytes(provider_export),
        "activation_provider_execution_list.csv",
        "text/csv",
    )
    d2.download_button(
        "导出内部记录清单",
        csv_bytes(internal_export),
        "activation_internal_record_list.csv",
        "text/csv",
    )

    tab_overview, tab_area, tab_merchants = st.tabs(["总览", "区域", "商户明细"])
    with tab_overview:
        c1, c2 = st.columns(2)
        with c1:
            severity = _distribution(filtered, "decay_band", value_map=DECAY_BAND_LABELS)
            render_echart(
                donut_option(severity, label="label", value="count", title="活跃等级", color_map=SEVERITY_DISPLAY_COLORS),
                key="chart_act_severity",
                height=330,
            )
        with c2:
            country = _distribution(filtered, "scope_country", value_map=COUNTRY_LABELS)
            render_echart(donut_option(country, label="label", value="count", title="国家分布"), key="chart_act_country", height=330)

        activity = _activity_windows(filtered)
        render_echart(
            simple_bar_option(activity, x="window", y="txn_count", title="2026 Q1 月度交易频次", color=PALETTE["cyan"]),
            key="chart_act_windows",
            height=330,
        )
        industry = _distribution(filtered, "mcc_major_industry").head(14)
        render_echart(treemap_option(industry, label="label", value="count", title="行业分布"), key="chart_act_industry", height=360)

    with tab_area:
        area = _area_rollup(filtered)
        render_echart(
            horizontal_bar_option(
                area.head(20),
                label="geo_reporting_name",
                value="low_activity_count",
                title="下滑区域排名",
                color=PALETTE["red"],
            ),
            key="chart_act_area_rank",
            height=560,
        )
        st.dataframe(display_table(area), use_container_width=True, hide_index=True)

    with tab_merchants:
        display = _select_columns(
            filtered,
            [
                "merchant_id",
                "merchant_name",
                "institution_name",
                "geo_country",
                "geo_state",
                "geo_city",
                "geo_suburb",
                "geo_postcode",
                "geo_reporting_level_label",
                "geo_reporting_name",
                "nz_geo_area",
                "nz_business_cluster",
                "mcc_major_industry",
                "trade_amt_prev_3m",
                "trade_amt_prev_2m",
                "trade_amt_prev_1m",
                "trade_cnt_prev_3m",
                "trade_cnt_prev_2m",
                "trade_cnt_prev_1m",
                "decay_band",
                "priority_label",
                "address",
            ],
        )
        st.dataframe(display_table(display), use_container_width=True, hide_index=True)


def _sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader("活跃监测筛选")
    filtered = df

    selected_country = mapped_multiselect_filter("国家", filtered, "geo_country", key="act_country", value_map=COUNTRY_LABELS)
    if selected_country:
        filtered = filtered[filtered["geo_country"].astype(str).isin(selected_country)]

    filtered = _apply_geo_filters(filtered)

    for label, column, key in (
        ("机构", "institution_name", "act_institution"),
        ("行业", "mcc_major_industry", "act_industry"),
        ("活跃等级", "decay_band", "act_severity"),
    ):
        if column == "decay_band":
            selected = mapped_multiselect_filter(label, filtered, column, key=key, value_map=DECAY_BAND_LABELS)
        else:
            selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]

    keyword = st.sidebar.text_input("商户/机构关键词", key="act_query")
    return apply_text_filter(
        filtered,
        ["merchant_id", "merchant_name", "institution_name", "geo_reporting_name", "geo_city", "geo_suburb"],
        keyword,
    )


def _apply_geo_filters(df: pd.DataFrame) -> pd.DataFrame:
    scope = country_scope(df)
    if scope == "NZ":
        return _apply_nz_geo_filters(df)
    if scope == "MIXED":
        selected_city = multiselect_filter("城市", df, "geo_city", key="act_geo_city")
        filtered = df[df["geo_city"].astype(str).isin(selected_city)] if selected_city else df
        if selected_city and country_scope(filtered) == "NZ":
            return _apply_nz_geo_filters(filtered, selected_city=selected_city)
        if selected_city and country_scope(filtered) == "AU":
            return _apply_standard_geo_filters(filtered, skip_columns={"geo_city"})
        return filtered
    return _apply_standard_geo_filters(df)


def _apply_nz_geo_filters(df: pd.DataFrame, *, selected_city: list[str] | None = None) -> pd.DataFrame:
    filtered = df
    if selected_city is None:
        selected_city = multiselect_filter("城市", filtered, "geo_city", key="act_geo_city")
        if selected_city:
            filtered = filtered[filtered["geo_city"].astype(str).isin(selected_city)]

    area_key = "act_nz_geo_area"
    if not selected_city:
        disabled_multiselect_filter(
            "NZ 地理片区",
            key=area_key,
            help_text="请先选择城市，之后才能选择 NZ 地理片区。",
        )
    elif not options(filtered, "nz_geo_area"):
        disabled_multiselect_filter(
            "NZ 地理片区",
            key=area_key,
            help_text="所选城市暂无已审核的 NZ 地理片区。",
        )
    else:
        selected_area = multiselect_filter("NZ 地理片区", filtered, "nz_geo_area", key=area_key)
        if selected_area:
            filtered = filtered[filtered["nz_geo_area"].astype(str).isin(selected_area)]

    for label, column, key in (
        ("NZ 商圈集群", "nz_business_cluster", "act_nz_cluster"),
        ("街区", "geo_suburb", "act_geo_suburb"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]
    return filtered


def _apply_standard_geo_filters(df: pd.DataFrame, *, skip_columns: set[str] | None = None) -> pd.DataFrame:
    filtered = df
    skip_columns = skip_columns or set()
    for spec in sidebar_geo_filter_specs(country_scope(filtered)):
        if spec.column in skip_columns:
            continue
        selected = multiselect_filter(spec.label, filtered, spec.column, key=f"act_{spec.key_suffix}")
        if selected:
            filtered = filtered[filtered[spec.column].astype(str).isin(selected)]
    return filtered


def _normalize_numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in (
        "trade_cnt_prev_3m",
        "trade_cnt_prev_2m",
        "trade_cnt_prev_1m",
        "trade_amt_prev_3m",
        "trade_amt_prev_2m",
        "trade_amt_prev_1m",
        "eligible_low_activity_flag",
        "activity_decay_score",
        "candidate_rank",
    ):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
    return out


def _with_priority_label(df: pd.DataFrame) -> pd.DataFrame:
    if "decay_band" not in df.columns:
        return df
    out = df.copy()
    out["priority_label"] = out["decay_band"].astype(str).map(PRIORITY_LABELS).fillna(out["decay_band"].astype(str))
    return out


def _with_frequency_decline_band(df: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_cnt_prev_3m", "trade_cnt_prev_2m", "trade_cnt_prev_1m"}
    if not required.issubset(df.columns):
        return df
    out = df.copy()
    bands: list[str] = []
    scores: list[float] = []
    for row in out.to_dict("records"):
        band, score = _classify_frequency_decline(
            jan=float(row.get("trade_cnt_prev_3m") or 0),
            feb=float(row.get("trade_cnt_prev_2m") or 0),
            mar=float(row.get("trade_cnt_prev_1m") or 0),
        )
        bands.append(band)
        scores.append(score)
    out["decay_band"] = bands
    out["activity_decay_score"] = scores
    out["eligible_low_activity_flag"] = out["trade_cnt_prev_3m"].fillna(0).astype(float) > 0
    return out


def _classify_frequency_decline(*, jan: float, feb: float, mar: float) -> tuple[str, float]:
    if jan <= 0:
        return "stable", 0.0
    if feb > 0:
        ratio = mar / feb
        if mar == 0:
            return "severe", 1.0
        if ratio <= 0.35:
            return "high", 0.82
        if ratio <= 0.7:
            return "medium", 0.58
        return "stable", 0.2
    if mar == 0:
        return "severe", 0.92
    if mar <= jan * 0.5:
        return "medium", 0.52
    return "stable", 0.2


def _distribution(df: pd.DataFrame, column: str, *, value_map: dict[str, str] | None = None) -> pd.DataFrame:
    if column not in df.columns:
        return pd.DataFrame(columns=["label", "count"])
    out = df[column].fillna("UNKNOWN").astype(str).value_counts().rename_axis("label").reset_index(name="count")
    if value_map:
        out["label"] = out["label"].map(lambda value: label_value(value, value_map))
    else:
        out["label"] = out["label"].replace({"UNKNOWN": "未分类"})
    return out


def _activity_windows(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"window": WINDOW_LABELS["prev_3m"], "txn_count": sum_number(df, "trade_cnt_prev_3m")},
            {"window": WINDOW_LABELS["prev_2m"], "txn_count": sum_number(df, "trade_cnt_prev_2m")},
            {"window": WINDOW_LABELS["prev_1m"], "txn_count": sum_number(df, "trade_cnt_prev_1m")},
        ]
    )


def _area_rollup(df: pd.DataFrame) -> pd.DataFrame:
    if "geo_reporting_name" not in df.columns:
        return pd.DataFrame()
    working = df.copy()
    working["geo_reporting_name"] = working["geo_reporting_name"].fillna("").astype(str).str.strip()
    working.loc[working["geo_reporting_name"] == "", "geo_reporting_name"] = "未分类"
    grouped = working.groupby(["geo_country", "geo_reporting_level_label", "geo_reporting_name"], dropna=False).agg(
        merchant_count=("merchant_id", "count"),
        eligible_count=("eligible_low_activity_flag", "sum"),
        low_activity_count=("decay_band", lambda s: s.astype(str).isin(LOW_ACTIVITY_BANDS).sum()),
        severe_count=("decay_band", lambda s: (s.astype(str) == "severe").sum()),
    )
    grouped["low_activity_ratio"] = grouped["low_activity_count"] / grouped["eligible_count"].replace(0, pd.NA)
    return grouped.reset_index().sort_values(["low_activity_count", "merchant_count"], ascending=False)


def _select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[[column for column in columns if column in df.columns]]
