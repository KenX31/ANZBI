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
from filters import apply_text_filter, disabled_multiselect_filter, multiselect_filter, options
from geography import country_scope, sidebar_geo_filter_specs, with_reporting_geography
from metrics import count_flag, format_int, format_pct, rate, sum_number


DEFAULT_MONTH_WINDOW = 6
ONLINE_SCOPE_EXCLUDE = "Exclude ONLINE"
ONLINE_SCOPE_ALL = "All channels"
ONLINE_SCOPE_ONLY = "Only ONLINE"


def render_new_intake_page(data: dict[str, object]) -> None:
    rows = with_reporting_geography(
        data["rows"].copy(),  # type: ignore[index, union-attr]
        country_columns=["analysis_country", "country_group", "merchant_country_code"],
    )
    if rows.empty:
        st.warning("No New Intake data is available.")
        return

    st.header("New Intake")
    st.caption("Cohort view: activation means the merchant traded within 30 days after onboarding.")
    st.info(
        "默认视图：最近 6 个 cohort 月，已排除 Zhenxing 和 ONLINE；如需查看完整口径，可在左侧筛选器调整。"
    )

    filtered = _sidebar_filters(rows)
    filtered = _normalize_numeric(filtered)

    total = len(filtered)
    active = count_flag(filtered, "active_30d_flag", 1)
    latest_month = _latest_month(filtered) if total else "-"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Merchants", format_int(total))
    c2.metric("30d Active", format_pct(rate(active, total)))
    c3.metric("Latest", str(latest_month))
    c4.metric("30d Txns", format_int(sum_number(filtered, "txn_count_30d")))

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
            "channel_type",
            "active_30d_flag",
            "txn_count_30d",
            "txn_amount_30d",
        ]
        st.dataframe(_select_columns(filtered, display_columns), use_container_width=True, hide_index=True)


def _sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader("New Intake Filters")
    st.sidebar.caption("Default: latest 6 cohort months, excluding Zhenxing and ONLINE.")
    filtered = df

    months = _month_options(df)
    if months:
        default_start, default_end = _default_month_range(months)
        start, end = st.sidebar.select_slider(
            "Cohort month range",
            options=months,
            value=(default_start, default_end),
            key="ni_month_range_recent6_v2",
            help="Default range is the latest 6 available cohort months.",
        )
        filtered = _filter_month_range(filtered, start, end)

    selected_country = multiselect_filter("Country", filtered, "geo_country", key="ni_country")
    if selected_country:
        filtered = filtered[filtered["geo_country"].astype(str).isin(selected_country)]

    filtered = _apply_geo_filters(filtered)

    zhenxing = st.sidebar.selectbox(
        "Zhenxing",
        ("All", "Only Zhenxing", "Exclude Zhenxing"),
        index=2,
        key="ni_zhenxing_default_exclude",
        help="Default excludes Zhenxing merchants from the New Intake working view.",
    )
    if "is_zhenxing" in filtered.columns:
        filtered = _apply_zhenxing_scope(filtered, zhenxing)

    online_scope = st.sidebar.selectbox(
        "Online scope",
        (ONLINE_SCOPE_EXCLUDE, ONLINE_SCOPE_ALL, ONLINE_SCOPE_ONLY),
        index=0,
        key="ni_online_scope_default_exclude",
        help="Default excludes channel_type=ONLINE. Switch to All channels to include ONLINE.",
    )
    filtered = _apply_online_scope(filtered, online_scope)

    for label, column, key in (
        ("Institution", "institution_standard", "ni_institution"),
        ("Channel", "channel_type", "ni_channel_scope"),
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

    query = st.sidebar.text_input("Merchant / institution keyword", key="ni_query")
    return apply_text_filter(
        filtered,
        [
            "merchant_id",
            "merchant_company_name",
            "merchant_short_name",
            "institution_standard",
            "institution_name",
            "geo_reporting_name",
            "geo_city",
            "geo_suburb",
        ],
        query,
    )


def _apply_geo_filters(df: pd.DataFrame) -> pd.DataFrame:
    scope = country_scope(df)
    if scope == "NZ":
        return _apply_nz_geo_filters(df)
    if scope == "MIXED":
        selected_city = multiselect_filter("City", df, "geo_city", key="ni_geo_city")
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
        selected_city = multiselect_filter("City", filtered, "geo_city", key="ni_geo_city")
        if selected_city:
            filtered = filtered[filtered["geo_city"].astype(str).isin(selected_city)]

    area_key = "ni_nz_geo_area"
    if not selected_city:
        disabled_multiselect_filter(
            "NZ geo area",
            key=area_key,
            help_text="Select City first to enable NZ geo area.",
        )
    elif not options(filtered, "nz_geo_area"):
        disabled_multiselect_filter(
            "NZ geo area",
            key=area_key,
            help_text="Selected City has no reviewed NZ geo area.",
        )
    else:
        selected_area = multiselect_filter("NZ geo area", filtered, "nz_geo_area", key=area_key)
        if selected_area:
            filtered = filtered[filtered["nz_geo_area"].astype(str).isin(selected_area)]

    for label, column, key in (
        ("NZ cluster", "nz_business_cluster", "ni_nz_cluster"),
        ("Suburb", "geo_suburb", "ni_geo_suburb"),
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
        selected = multiselect_filter(spec.label, filtered, spec.column, key=f"ni_{spec.key_suffix}")
        if selected:
            filtered = filtered[filtered[spec.column].astype(str).isin(selected)]
    return filtered


def _normalize_numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in ("txn_count_30d", "txn_amount_30d", "active_30d_flag"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
    return out


def _month_options(df: pd.DataFrame) -> list[str]:
    if "intake_month" not in df.columns:
        return []
    values = df["intake_month"].dropna().astype(str)
    months = {_month_label(value) for value in values if value.strip() and value.strip().lower() != "nan"}
    months = {month for month in months if month}
    return sorted(months, key=_month_sort_key)


def _default_month_range(months: list[str], window: int = DEFAULT_MONTH_WINDOW) -> tuple[str, str]:
    start_index = max(0, len(months) - window)
    return months[start_index], months[-1]


def _filter_month_range(df: pd.DataFrame, start: object, end: object) -> pd.DataFrame:
    if "intake_month" not in df.columns:
        return df
    start_key = _month_period_key(start)
    end_key = _month_period_key(end)
    if start_key > end_key:
        start_key, end_key = end_key, start_key
    mask = df["intake_month"].fillna("").astype(str).map(lambda value: start_key <= _month_period_key(value) <= end_key)
    return df[mask]


def _month_sort_key(value: object) -> tuple[int, int, str]:
    text = str(value or "").strip()
    normalized = text.replace("-", ".").replace("/", ".")
    parts = normalized.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        year = int(parts[0])
        month_text = parts[1]
        # Current source contract is YYYY.MM. If a previous CSV inference turned
        # 2025.10 into 2025.1, treat the non-padded .1 as October.
        month = 10 if month_text == "1" else int(month_text)
        if 1 <= month <= 12:
            return year, month, text
    return 9999, 99, text


def _month_label(value: object) -> str:
    year, month, _ = _month_sort_key(value)
    if year == 9999:
        return str(value or "").strip()
    return f"{year}.{month:02d}"


def _month_period_key(value: object) -> tuple[int, int]:
    year, month, _ = _month_sort_key(value)
    return year, month


def _latest_month(df: pd.DataFrame) -> str:
    months = _month_options(df)
    return months[-1] if months else "-"


def _apply_online_scope(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    if "channel_type" not in df.columns:
        return df
    channel = df["channel_type"].fillna("").astype(str).str.upper()
    if scope == ONLINE_SCOPE_EXCLUDE:
        return df[channel != "ONLINE"]
    if scope == ONLINE_SCOPE_ONLY:
        return df[channel == "ONLINE"]
    return df


def _apply_zhenxing_scope(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    if "is_zhenxing" not in df.columns:
        return df
    values = df["is_zhenxing"].fillna("").astype(str)
    if scope == "Only Zhenxing":
        return df[values == "1"]
    if scope == "Exclude Zhenxing":
        return df[values == "0"]
    return df


def _monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("intake_month", dropna=False).agg(
        merchant_count=("merchant_id", "count"),
        active_30d_count=("active_30d_flag", lambda s: (pd.to_numeric(s, errors="coerce").fillna(0) == 1).sum()),
        txn_amount_30d=("txn_amount_30d", "sum"),
    )
    grouped["active_30d_rate"] = grouped["active_30d_count"] / grouped["merchant_count"].replace(0, pd.NA)
    return _sort_by_month(grouped.reset_index())


def _country_monthly(df: pd.DataFrame) -> pd.DataFrame:
    if "analysis_country" not in df.columns:
        return pd.DataFrame()
    pivot = (
        df.pivot_table(index="intake_month", columns="analysis_country", values="merchant_id", aggfunc="count", fill_value=0)
        .reset_index()
    )
    pivot.columns = [str(col) for col in pivot.columns]
    return _sort_by_month(pivot)


def _sort_by_month(df: pd.DataFrame) -> pd.DataFrame:
    if "intake_month" not in df.columns or df.empty:
        return df
    out = df.copy()
    out["_month_order"] = out["intake_month"].astype(str).map(_month_sort_key)
    return out.sort_values("_month_order").drop(columns="_month_order")


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
