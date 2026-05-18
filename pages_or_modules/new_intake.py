from __future__ import annotations

import pandas as pd
import streamlit as st

from charts import (
    PALETTE,
    combo_line_bar_option,
    donut_option,
    empty_chart,
    horizontal_bar_option,
    render_echart,
    stacked_bar_option,
    treemap_option,
)
from exports import csv_bytes, new_intake_internal_export, new_intake_provider_export
from filters import apply_text_filter, multiselect_filter, options
from metrics import count_flag, format_int, format_money, format_pct, rate, sum_number


def render_new_intake_page(data: dict[str, object]) -> None:
    rows = data["rows"].copy()  # type: ignore[index, union-attr]
    if rows.empty:
        st.warning("No New Intake data is available.")
        return

    st.header("New Intake")
    st.caption("Cohort view: activation means the merchant traded within 30 days after onboarding.")

    filtered = _sidebar_filters(rows)
    filtered = _normalize_numeric(filtered)

    total = len(filtered)
    active = count_flag(filtered, "active_30d_flag", 1)
    latest_month = filtered["intake_month"].max() if "intake_month" in filtered.columns and total else "-"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Merchants", format_int(total))
    c2.metric("30d Active", format_pct(rate(active, total)))
    c3.metric("Latest", str(latest_month))
    c4.metric("30d Amount", format_money(sum_number(filtered, "txn_amount_30d")))

    if filtered.empty:
        st.info("No merchants match the current filters.")
        return

    provider_export = new_intake_provider_export(filtered)
    internal_export = new_intake_internal_export(filtered)
    d1, d2 = st.columns(2)
    d1.download_button(
        "导出服务商执行清单",
        csv_bytes(provider_export),
        "new_intake_provider_execution_list.csv",
        "text/csv",
    )
    d2.download_button(
        "导出内部记录清单",
        csv_bytes(internal_export),
        "new_intake_internal_record_list.csv",
        "text/csv",
    )

    tab_overview, tab_institutions, tab_merchants = st.tabs(["Overview", "Institutions", "Merchants"])
    with tab_overview:
        monthly = _monthly_trend(filtered)
        render_echart(
            combo_line_bar_option(
                monthly,
                x="intake_month",
                bar_y="merchant_count",
                line_y="active_30d_rate",
                title="Monthly intake and 30d activation",
                bar_name="Intake",
                line_name="30d active rate",
            ),
            key="chart_ni_monthly_combo",
            height=390,
        )

        country_month = _country_monthly(filtered)
        if country_month.empty:
            empty_chart()
        else:
            render_echart(
                stacked_bar_option(
                    country_month,
                    category="intake_month",
                    value_columns=[col for col in country_month.columns if col != "intake_month"],
                    title="Monthly intake by country",
                ),
                key="chart_ni_country_stack",
                height=360,
            )

        c1, c2 = st.columns(2)
        with c1:
            channel = _distribution(filtered, "channel_type")
            render_echart(donut_option(channel, label="label", value="count", title="Channel"), key="chart_ni_channel", height=330)
        with c2:
            industry = _distribution(filtered, "mcc_major_industry").head(14)
            render_echart(treemap_option(industry, label="label", value="count", title="Industry mix"), key="chart_ni_industry", height=330)

    with tab_institutions:
        inst = _institution_rollup(filtered)
        render_echart(
            horizontal_bar_option(
                inst.head(15),
                label="institution_standard",
                value="merchant_count",
                title="Top institutions",
                color=PALETTE["cyan"],
            ),
            key="chart_ni_top_institutions",
            height=470,
        )
        st.dataframe(inst, use_container_width=True, hide_index=True)

    with tab_merchants:
        display_columns = [
            "intake_month",
            "merchant_id",
            "merchant_short_name",
            "institution_standard",
            "analysis_country",
            "business_city",
            "business_suburb",
            "geo_area",
            "business_cluster",
            "mcc_major_industry",
            "channel_type",
            "active_30d_flag",
            "txn_count_30d",
            "txn_amount_30d",
        ]
        st.dataframe(_select_columns(filtered, display_columns), use_container_width=True, hide_index=True)


def _sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader("New Intake Filters")
    filtered = df

    months = options(df, "intake_month")
    if months:
        start, end = st.sidebar.select_slider(
            "Cohort month range",
            options=months,
            value=(months[0], months[-1]),
            key="ni_month_range",
        )
        filtered = filtered[
            (filtered["intake_month"].astype(str) >= str(start))
            & (filtered["intake_month"].astype(str) <= str(end))
        ]

    for label, column, key in (
        ("Country", "analysis_country", "ni_country"),
        ("City", "business_city", "ni_city"),
        ("Suburb", "business_suburb", "ni_suburb"),
        ("Geo area", "geo_area", "ni_geo_area"),
        ("Cluster", "business_cluster", "ni_cluster"),
        ("Institution", "institution_standard", "ni_institution"),
        ("Channel", "channel_type", "ni_channel"),
        ("Industry", "mcc_major_industry", "ni_industry"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]

    status = st.sidebar.selectbox("Activation status", ("All", "Active", "Inactive"), key="ni_active")
    if status == "Active":
        filtered = filtered[filtered["active_30d_flag"].astype(str) == "1"]
    elif status == "Inactive":
        filtered = filtered[filtered["active_30d_flag"].astype(str) == "0"]

    zhenxing = st.sidebar.selectbox("Zhenxing", ("All", "Only Zhenxing", "Exclude Zhenxing"), key="ni_zhenxing")
    if "is_zhenxing" in filtered.columns:
        if zhenxing == "Only Zhenxing":
            filtered = filtered[filtered["is_zhenxing"].astype(str) == "1"]
        elif zhenxing == "Exclude Zhenxing":
            filtered = filtered[filtered["is_zhenxing"].astype(str) == "0"]

    query = st.sidebar.text_input("Merchant / institution keyword", key="ni_query")
    return apply_text_filter(
        filtered,
        ["merchant_id", "merchant_company_name", "merchant_short_name", "institution_standard", "institution_name"],
        query,
    )


def _normalize_numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in ("txn_count_30d", "txn_amount_30d", "active_30d_flag"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
    return out


def _monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("intake_month", dropna=False).agg(
        merchant_count=("merchant_id", "count"),
        active_30d_count=("active_30d_flag", lambda s: (pd.to_numeric(s, errors="coerce").fillna(0) == 1).sum()),
        txn_amount_30d=("txn_amount_30d", "sum"),
    )
    grouped["active_30d_rate"] = grouped["active_30d_count"] / grouped["merchant_count"].replace(0, pd.NA)
    return grouped.reset_index()


def _country_monthly(df: pd.DataFrame) -> pd.DataFrame:
    if "analysis_country" not in df.columns:
        return pd.DataFrame()
    pivot = (
        df.pivot_table(index="intake_month", columns="analysis_country", values="merchant_id", aggfunc="count", fill_value=0)
        .reset_index()
        .sort_values("intake_month")
    )
    pivot.columns = [str(col) for col in pivot.columns]
    return pivot


def _institution_rollup(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("institution_standard", dropna=False).agg(
        merchant_count=("merchant_id", "count"),
        active_30d_count=("active_30d_flag", lambda s: (pd.to_numeric(s, errors="coerce").fillna(0) == 1).sum()),
        txn_count_30d=("txn_count_30d", "sum"),
        txn_amount_30d=("txn_amount_30d", "sum"),
    )
    grouped["active_30d_rate"] = grouped["active_30d_count"] / grouped["merchant_count"].replace(0, pd.NA)
    return grouped.reset_index().sort_values("merchant_count", ascending=False)


def _distribution(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in df.columns:
        return pd.DataFrame(columns=["label", "count"])
    return (
        df[column]
        .fillna("UNKNOWN")
        .astype(str)
        .value_counts()
        .rename_axis("label")
        .reset_index(name="count")
    )


def _select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[[column for column in columns if column in df.columns]]
