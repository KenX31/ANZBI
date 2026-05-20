from __future__ import annotations

import pandas as pd
import streamlit as st

from auth import can_export_data, render_export_restricted_notice
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
from filters import apply_in_filter, apply_text_filter, disabled_multiselect_filter, ka_scope_filter, mapped_multiselect_filter, multiselect_filter, options
from geography import country_scope, sidebar_geo_filter_specs, with_reporting_geography
from metrics import count_flag, format_int, format_pct, rate, sum_number
from ui_labels import CHANNEL_LABELS, COUNTRY_LABELS, display_table, label_value


DEFAULT_MONTH_WINDOW = 6
ONLINE_SCOPE_EXCLUDE = "排除线上"
ONLINE_SCOPE_ALL = "全部渠道"
ONLINE_SCOPE_ONLY = "只看线上"


def render_new_intake_page(data: dict[str, object]) -> None:
    rows = with_reporting_geography(
        data["rows"].copy(),  # type: ignore[index, union-attr]
        country_columns=["analysis_country", "country_group", "merchant_country_code"],
    )
    if rows.empty:
        st.warning("没有可用的新进件数据。")
        return

    st.header("新进件")
    st.caption(
        "进件月口径：按商户接入月份归档；激活表示商户在接入后30天内产生交易。"
        "数据按月更新，下一次更新计划为 2026.6.1。"
    )
    st.info(
        "默认视图：最近 6 个进件月，已排除圳兴商户和线上商户；如需查看完整口径，可在左侧筛选器调整。"
    )

    filtered = _sidebar_filters(rows)
    filtered = _normalize_numeric(filtered)

    total = len(filtered)
    active = count_flag(filtered, "active_30d_flag", 1)
    latest_month = _latest_month(filtered) if total else "-"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("商户数", format_int(total))
    c2.metric("接入后30天激活率", format_pct(rate(active, total)))
    c3.metric("最新月份", str(latest_month))
    c4.metric("接入后30天交易笔数", format_int(sum_number(filtered, "txn_count_30d")))

    if filtered.empty:
        st.info("当前筛选下没有匹配商户。")
        return

    if can_export_data():
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
    else:
        render_export_restricted_notice()

    tab_overview, tab_institutions, tab_merchants = st.tabs(["总览", "机构", "商户明细"])
    with tab_overview:
        monthly = _monthly_trend(filtered)
        render_echart(
            combo_line_bar_option(
                monthly,
                x="intake_month",
                bar_y="merchant_count",
                line_y="active_30d_rate",
                title="月度进件与接入后30天激活率",
                bar_name="进件商户数",
                line_name="接入后30天激活率",
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
                    title="按国家月度进件",
                ),
                key="chart_ni_country_stack",
                height=360,
            )

        c1, c2 = st.columns(2)
        with c1:
            channel = _distribution(filtered, "channel_type", value_map=CHANNEL_LABELS)
            render_echart(donut_option(channel, label="label", value="count", title="渠道分布"), key="chart_ni_channel", height=330)
        with c2:
            industry = _industry_activation_treemap(filtered).head(14)
            render_echart(
                treemap_option(
                    industry,
                    label="label",
                    value="merchant_count",
                    title="行业分布：面积=当前筛选商户占比，颜色=接入后30天激活率",
                    color_by="active_30d_rate",
                    color_name="接入后30天激活率",
                    high_is_good=True,
                ),
                key="chart_ni_industry",
                height=330,
            )

    with tab_institutions:
        inst = _institution_rollup(filtered)
        render_echart(
            horizontal_bar_option(
                inst.head(15),
                label="institution_standard",
                value="merchant_count",
                title="机构排名",
                color=PALETTE["cyan"],
            ),
            key="chart_ni_top_institutions",
            height=470,
        )
        st.dataframe(display_table(inst), use_container_width=True, hide_index=True)

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
            "nz_geo_area",
            "nz_business_cluster",
            "mcc_major_industry",
            "channel_type",
            "active_30d_flag",
            "txn_count_30d",
            "txn_amount_30d",
        ]
        st.dataframe(display_table(_select_columns(filtered, display_columns)), use_container_width=True, hide_index=True)


def _sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader("新进件筛选")
    st.sidebar.caption("默认：最近 6 个进件月，排除圳兴商户和线上商户。")
    filtered = df

    months = _month_options(df)
    if months:
        default_start, default_end = _default_month_range(months)
        start, end = st.sidebar.select_slider(
            "进件月份范围",
            options=months,
            value=(default_start, default_end),
            key="ni_month_range_recent6_v2",
            help="默认使用数据中最新的 6 个进件月。",
        )
        filtered = _filter_month_range(filtered, start, end)

    selected_country = mapped_multiselect_filter("国家", filtered, "geo_country", key="ni_country", value_map=COUNTRY_LABELS)
    if selected_country:
        filtered = apply_in_filter(filtered, "geo_country", selected_country)

    filtered = ka_scope_filter(filtered, key="ni_ka_scope")

    filtered = _apply_geo_filters(filtered)

    zhenxing = st.sidebar.selectbox(
        "圳兴商户",
        ("全部", "只看圳兴", "排除圳兴"),
        index=2,
        key="ni_zhenxing_default_exclude",
        help="默认从新进件工作视图中排除圳兴商户。",
    )
    if "is_zhenxing" in filtered.columns:
        filtered = _apply_zhenxing_scope(filtered, zhenxing)

    online_scope = st.sidebar.selectbox(
        "线上渠道",
        (ONLINE_SCOPE_EXCLUDE, ONLINE_SCOPE_ALL, ONLINE_SCOPE_ONLY),
        index=0,
        key="ni_online_scope_default_exclude",
        help="默认排除线上商户。切换到全部渠道可纳入线上商户。",
    )
    filtered = _apply_online_scope(filtered, online_scope)

    for label, column, key in (
        ("机构", "institution_standard", "ni_institution"),
        ("渠道", "channel_type", "ni_channel_scope"),
        ("行业", "mcc_major_industry", "ni_industry"),
    ):
        if column == "channel_type":
            selected = mapped_multiselect_filter(label, filtered, column, key=key, value_map=CHANNEL_LABELS)
        else:
            selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = apply_in_filter(filtered, column, selected)

    status = st.sidebar.selectbox("接入后30天激活状态", ("全部", "已激活", "未激活"), key="ni_active")
    if status == "已激活":
        filtered = filtered[filtered["active_30d_flag"].astype(str) == "1"]
    elif status == "未激活":
        filtered = filtered[filtered["active_30d_flag"].astype(str) == "0"]

    query = st.sidebar.text_input("商户/机构关键词", key="ni_query")
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
        selected_city = multiselect_filter("城市", df, "geo_city", key="ni_geo_city")
        filtered = apply_in_filter(df, "geo_city", selected_city) if selected_city else df
        if selected_city and country_scope(filtered) == "NZ":
            return _apply_nz_geo_filters(filtered, selected_city=selected_city)
        if selected_city and country_scope(filtered) == "AU":
            return _apply_standard_geo_filters(filtered, skip_columns={"geo_city"})
        return filtered
    return _apply_standard_geo_filters(df)


def _apply_nz_geo_filters(df: pd.DataFrame, *, selected_city: list[str] | None = None) -> pd.DataFrame:
    filtered = df
    if selected_city is None:
        selected_city = multiselect_filter("城市", filtered, "geo_city", key="ni_geo_city")
        if selected_city:
            filtered = apply_in_filter(filtered, "geo_city", selected_city)

    area_key = "ni_nz_geo_area"
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
            filtered = apply_in_filter(filtered, "nz_geo_area", selected_area)

    for label, column, key in (
        ("NZ 商圈集群", "nz_business_cluster", "ni_nz_cluster"),
        ("街区", "geo_suburb", "ni_geo_suburb"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = apply_in_filter(filtered, column, selected)
    return filtered


def _apply_standard_geo_filters(df: pd.DataFrame, *, skip_columns: set[str] | None = None) -> pd.DataFrame:
    filtered = df
    skip_columns = skip_columns or set()
    for spec in sidebar_geo_filter_specs(country_scope(filtered)):
        if spec.column in skip_columns:
            continue
        selected = multiselect_filter(spec.label, filtered, spec.column, key=f"ni_{spec.key_suffix}")
        if selected:
            filtered = apply_in_filter(filtered, spec.column, selected)
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
    if scope == "只看圳兴":
        return df[values == "1"]
    if scope == "排除圳兴":
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
    pivot = pivot.rename(columns={key: value for key, value in COUNTRY_LABELS.items() if key in pivot.columns})
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


def _distribution(df: pd.DataFrame, column: str, *, value_map: dict[str, str] | None = None) -> pd.DataFrame:
    if column not in df.columns:
        return pd.DataFrame(columns=["label", "count"])
    out = (
        df[column]
        .fillna("UNKNOWN")
        .astype(str)
        .value_counts()
        .rename_axis("label")
        .reset_index(name="count")
    )
    if value_map:
        out["label"] = out["label"].map(lambda value: label_value(value, value_map))
    else:
        out["label"] = out["label"].replace({"UNKNOWN": "未分类"})
    return out


def _industry_activation_treemap(df: pd.DataFrame) -> pd.DataFrame:
    if "mcc_major_industry" not in df.columns:
        return pd.DataFrame(columns=["label", "merchant_count", "active_30d_count", "active_30d_rate"])
    working = df.copy()
    working["label"] = working["mcc_major_industry"].fillna("").astype(str).str.strip()
    working.loc[working["label"].isin(["", "nan", "None", "UNKNOWN"]), "label"] = "未分类"
    grouped = working.groupby("label", dropna=False).agg(
        merchant_count=("merchant_id", "count"),
        active_30d_count=("active_30d_flag", lambda s: (pd.to_numeric(s, errors="coerce").fillna(0) == 1).sum()),
    )
    grouped["active_30d_rate"] = grouped["active_30d_count"] / grouped["merchant_count"].replace(0, pd.NA)
    return grouped.reset_index().sort_values("merchant_count", ascending=False)


def _select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[[column for column in columns if column in df.columns]]
