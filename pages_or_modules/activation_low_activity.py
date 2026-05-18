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
from filters import apply_text_filter, multiselect_filter
from metrics import format_int, format_pct, rate, sum_number


LOW_ACTIVITY_BANDS = {"severe", "high", "medium"}
PRIORITY_LABELS = {
    "severe": "优先铺设",
    "high": "重点铺设",
    "medium": "机会铺设",
    "stable": "维护经营",
}


def render_activation_page(data: dict[str, object]) -> None:
    rows = data["rows"].copy()  # type: ignore[index, union-attr]
    if rows.empty:
        st.warning("No Activation Low-Activity data is available.")
        return

    st.header("Activation Low-Activity")
    st.caption("Region-first BI: prev_3m > 0 is evaluable; prev_2m and prev_1m drive low-activity severity.")

    filtered = _sidebar_filters(rows)
    filtered = _normalize_numeric(_with_priority_label(filtered))
    eligible = int(sum_number(filtered, "eligible_low_activity_flag"))
    low_activity = int(filtered["decay_band"].astype(str).isin(LOW_ACTIVITY_BANDS).sum()) if "decay_band" in filtered else 0
    severe = int((filtered["decay_band"].astype(str) == "severe").sum()) if "decay_band" in filtered else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidates", format_int(len(filtered)))
    c2.metric("Evaluable", format_int(eligible))
    c3.metric("Low Activity", format_pct(rate(low_activity, eligible)))
    c4.metric("Severe", format_int(severe))

    if filtered.empty:
        st.info("No merchants match the current filters.")
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

    tab_overview, tab_area, tab_merchants = st.tabs(["Overview", "Areas", "Merchants"])
    with tab_overview:
        c1, c2 = st.columns(2)
        with c1:
            severity = _distribution(filtered, "decay_band")
            render_echart(
                donut_option(severity, label="label", value="count", title="Severity", color_map=SEVERITY_COLORS),
                key="chart_act_severity",
                height=330,
            )
        with c2:
            country = _distribution(filtered, "scope_country")
            render_echart(donut_option(country, label="label", value="count", title="Country"), key="chart_act_country", height=330)

        activity = _activity_windows(filtered)
        render_echart(
            simple_bar_option(activity, x="window", y="txn_count", title="1m / 2m / 3m activity", color=PALETTE["cyan"]),
            key="chart_act_windows",
            height=330,
        )
        industry = _distribution(filtered, "mcc_major_industry").head(14)
        render_echart(treemap_option(industry, label="label", value="count", title="Industry mix"), key="chart_act_industry", height=360)

    with tab_area:
        area = _area_rollup(filtered)
        render_echart(
            horizontal_bar_option(
                area.head(20),
                label="business_area",
                value="low_activity_count",
                title="Top low-activity areas",
                color=PALETTE["red"],
            ),
            key="chart_act_area_rank",
            height=560,
        )
        st.dataframe(area, use_container_width=True, hide_index=True)

    with tab_merchants:
        display = _select_columns(
            filtered,
            [
                "merchant_id",
                "merchant_name",
                "institution_name",
                "scope_country",
                "business_city",
                "business_suburb",
                "geo_area",
                "business_cluster",
                "business_area",
                "mcc_major_industry",
                "trade_cnt_prev_3m",
                "trade_cnt_prev_2m",
                "trade_cnt_prev_1m",
                "decay_band",
                "priority_label",
                "address",
            ],
        )
        st.dataframe(display, use_container_width=True, hide_index=True)


def _sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader("Activation Filters")
    filtered = df
    for label, column, key in (
        ("Country", "scope_country", "act_country"),
        ("City", "business_city", "act_city"),
        ("Suburb", "business_suburb", "act_suburb"),
        ("Geo area", "geo_area", "act_geo_area"),
        ("Cluster", "business_cluster", "act_cluster"),
        ("Business area", "business_area", "act_business_area"),
        ("Institution", "institution_name", "act_institution"),
        ("Industry", "mcc_major_industry", "act_industry"),
        ("Severity", "decay_band", "act_severity"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]

    keyword = st.sidebar.text_input("Merchant / institution keyword", key="act_query")
    return apply_text_filter(filtered, ["merchant_id", "merchant_name", "institution_name", "business_area"], keyword)


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


def _distribution(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in df.columns:
        return pd.DataFrame(columns=["label", "count"])
    return df[column].fillna("UNKNOWN").astype(str).value_counts().rename_axis("label").reset_index(name="count")


def _activity_windows(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"window": "prev_3m", "txn_count": sum_number(df, "trade_cnt_prev_3m")},
            {"window": "prev_2m", "txn_count": sum_number(df, "trade_cnt_prev_2m")},
            {"window": "prev_1m", "txn_count": sum_number(df, "trade_cnt_prev_1m")},
        ]
    )


def _area_rollup(df: pd.DataFrame) -> pd.DataFrame:
    if "business_area" not in df.columns:
        return pd.DataFrame()
    grouped = df.groupby(["scope_country", "business_area"], dropna=False).agg(
        merchant_count=("merchant_id", "count"),
        eligible_count=("eligible_low_activity_flag", "sum"),
        low_activity_count=("decay_band", lambda s: s.astype(str).isin(LOW_ACTIVITY_BANDS).sum()),
        severe_count=("decay_band", lambda s: (s.astype(str) == "severe").sum()),
    )
    grouped["low_activity_ratio"] = grouped["low_activity_count"] / grouped["eligible_count"].replace(0, pd.NA)
    return grouped.reset_index().sort_values(["low_activity_count", "merchant_count"], ascending=False)


def _select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[[column for column in columns if column in df.columns]]
