from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from charts import PALETTE, empty_chart, horizontal_bar_option, render_echart
from filters import apply_text_filter, mapped_multiselect_filter, multiselect_filter
from metrics import format_int, format_money, sum_number
from ui_labels import COUNTRY_LABELS, display_table


PAGE_ID = "rate_coupon_activity"
METRIC_OPTIONS = (
    "redeeming_submerchant_count",
    "redeemed_coupon_code_count_trade",
    "cost_money_yuan",
)

UI_TEXT = {
    "title": "重点汇率活动",
    "caption": (
        "按月监测 AU/NZ 汇率券重点批次的活跃核销商户、核销券码、订单和成本消耗，"
        "用于日常项目监控和后续预算申请参考。"
    ),
    "definition": (
        "商户活跃数为当月该批次发生核销的去重子商户数；核销券码数优先使用交易表去重券码数，"
        "并保留批次维表累计差分用券数作为校验口径。"
    ),
    "empty": "没有可用的重点汇率活动数据。",
    "empty_filter": "当前筛选下没有匹配的汇率活动数据。",
    "sidebar": "重点汇率活动筛选",
    "month_range": "月份范围",
    "country": "国家",
    "stock": "活动批次",
    "metric": "堆叠图指标",
    "keyword": "批次/国家/stockid 关键词",
    "tab_overview": "总览",
    "tab_stock": "批次",
    "tab_detail": "明细",
    "stock_count": "批次数",
    "latest_month": "最新月份",
    "latest_active_merchants": "最新月活跃商户数",
    "latest_redeemed_coupons": "最新月核销券码数",
    "latest_cost": "最新月成本",
    "active_trend": "月度核销活跃商户数趋势",
    "redeemed_trend": "月度核销券码数趋势",
    "cost_trend": "月度成本消耗趋势",
    "stock_stack": "按批次月度趋势",
    "stock_redeemed_rank": "批次累计核销券码数排名",
    "stock_cost_rank": "批次累计成本排名",
}

METRIC_LABELS = {
    "redeeming_submerchant_count": "活跃商户数",
    "redeemed_coupon_code_count_trade": "核销券码数",
    "cost_money_yuan": "成本金额",
}

NUMERIC_COLUMNS = (
    "month_order",
    "stock_sort_order",
    "issued_coupon_code_count",
    "used_coupon_code_count_stock_dim",
    "redeemed_coupon_code_count_trade",
    "redeeming_submerchant_count",
    "trade_order_count",
    "trade_row_count",
    "pay_amt_cny_yuan",
    "user_save_money_yuan",
    "cost_money_yuan",
    "redemption_gap_count",
    "redeemed_per_active_merchant",
    "cost_per_redeemed_coupon_yuan",
)


def render_rate_coupon_activity_page(data: dict[str, object]) -> None:
    monthly = _prepare_monthly(data["monthly"].copy())  # type: ignore[index, union-attr]
    metadata = _prepare_metadata(data.get("stock_metadata"))
    if monthly.empty:
        st.warning(UI_TEXT["empty"])
        return

    st.header(UI_TEXT["title"])
    st.caption(UI_TEXT["caption"])
    st.info(UI_TEXT["definition"])

    filtered = _sidebar_filters(monthly, metadata)
    metrics = summary_metrics(filtered)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(UI_TEXT["stock_count"], format_int(metrics["stock_count"]))
    c2.metric(UI_TEXT["latest_month"], metrics["latest_month"])
    c3.metric(UI_TEXT["latest_active_merchants"], format_int(metrics["latest_active_merchants"]))
    c4.metric(UI_TEXT["latest_redeemed_coupons"], format_int(metrics["latest_redeemed_coupons"]))
    c5.metric(UI_TEXT["latest_cost"], format_money(metrics["latest_cost"]))

    if filtered.empty:
        st.info(UI_TEXT["empty_filter"])
        return

    tab_overview, tab_stock, tab_detail = st.tabs(
        [UI_TEXT["tab_overview"], UI_TEXT["tab_stock"], UI_TEXT["tab_detail"]]
    )

    with tab_overview:
        trend = monthly_trend(filtered)
        c1, c2 = st.columns(2)
        with c1:
            render_echart(
                line_option(
                    trend,
                    x="month_label",
                    y="redeeming_submerchant_count",
                    title=UI_TEXT["active_trend"],
                    series_name=METRIC_LABELS["redeeming_submerchant_count"],
                    color=PALETTE["cyan"],
                ),
                key="chart_rate_coupon_active_trend",
                height=340,
            )
        with c2:
            render_echart(
                line_option(
                    trend,
                    x="month_label",
                    y="redeemed_coupon_code_count_trade",
                    title=UI_TEXT["redeemed_trend"],
                    series_name=METRIC_LABELS["redeemed_coupon_code_count_trade"],
                    color=PALETTE["green"],
                ),
                key="chart_rate_coupon_redeemed_trend",
                height=340,
            )

        c1, c2 = st.columns(2)
        with c1:
            render_echart(
                line_option(
                    trend,
                    x="month_label",
                    y="cost_money_yuan",
                    title=UI_TEXT["cost_trend"],
                    series_name=METRIC_LABELS["cost_money_yuan"],
                    color=PALETTE["blue"],
                ),
                key="chart_rate_coupon_cost_trend",
                height=340,
            )
        with c2:
            metric_key = st.radio(
                UI_TEXT["metric"],
                METRIC_OPTIONS,
                format_func=lambda value: METRIC_LABELS.get(str(value), str(value)),
                horizontal=True,
                key="rate_coupon_stack_metric",
            )
            render_echart(
                stacked_stock_option(
                    filtered,
                    metric=str(metric_key),
                    title=f"{UI_TEXT['stock_stack']}：{METRIC_LABELS[str(metric_key)]}",
                ),
                key=f"chart_rate_coupon_stock_stack_{metric_key}",
                height=340,
            )

    with tab_stock:
        totals = stock_totals(filtered)
        if totals.empty:
            empty_chart()
        else:
            c1, c2 = st.columns(2)
            with c1:
                render_echart(
                    horizontal_bar_option(
                        totals.sort_values("total_redeemed_coupon_code_count_trade", ascending=False).head(12),
                        label="stock_label",
                        value="total_redeemed_coupon_code_count_trade",
                        title=UI_TEXT["stock_redeemed_rank"],
                        color=PALETTE["green"],
                    ),
                    key="chart_rate_coupon_stock_redeemed_rank",
                    height=430,
                )
            with c2:
                render_echart(
                    horizontal_bar_option(
                        totals.sort_values("total_cost_money_yuan", ascending=False).head(12),
                        label="stock_label",
                        value="total_cost_money_yuan",
                        title=UI_TEXT["stock_cost_rank"],
                        color=PALETTE["blue"],
                    ),
                    key="chart_rate_coupon_stock_cost_rank",
                    height=430,
                )
            st.dataframe(display_table(totals), use_container_width=True, hide_index=True)

    with tab_detail:
        detail_columns = [
            "month_label",
            "country_group",
            "stock_label",
            "stock_id",
            "issued_coupon_code_count",
            "used_coupon_code_count_stock_dim",
            "redeemed_coupon_code_count_trade",
            "redeeming_submerchant_count",
            "trade_order_count",
            "trade_row_count",
            "pay_amt_cny_yuan",
            "user_save_money_yuan",
            "cost_money_yuan",
            "redemption_gap_count",
            "redeemed_per_active_merchant",
            "cost_per_redeemed_coupon_yuan",
        ]
        st.dataframe(display_table(_select_columns(filtered, detail_columns)), use_container_width=True, hide_index=True)


def _sidebar_filters(monthly: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader(UI_TEXT["sidebar"])
    filtered = monthly

    months = month_options(monthly)
    if months:
        start, end = st.sidebar.select_slider(
            UI_TEXT["month_range"],
            options=months,
            value=(months[0], months[-1]),
            key="rate_coupon_month_range",
        )
        filtered = filter_month_range(filtered, str(start), str(end))

    selected_country = mapped_multiselect_filter(
        UI_TEXT["country"],
        filtered,
        "country_group",
        key="rate_coupon_country",
        value_map=COUNTRY_LABELS,
    )
    if selected_country:
        filtered = filtered[filtered["country_group"].astype(str).isin(selected_country)]

    stock_labels = stock_label_map(metadata if not metadata.empty else filtered)
    selected_stock = mapped_multiselect_filter(
        UI_TEXT["stock"],
        filtered,
        "stock_id",
        key="rate_coupon_stock",
        value_map=stock_labels,
    )
    if selected_stock:
        filtered = filtered[filtered["stock_id"].astype(str).isin(selected_stock)]

    keyword = st.sidebar.text_input(UI_TEXT["keyword"], key="rate_coupon_query")
    return apply_text_filter(
        filtered,
        ["stock_id", "stock_key", "stock_name_cn", "stock_label", "country_group"],
        keyword,
    )


def _prepare_monthly(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in ("month_label", "stock_id", "stock_key", "stock_name_cn", "stock_label", "country_group"):
        if column not in out.columns:
            out[column] = ""
        out[column] = out[column].fillna("").astype(str)
    for column in NUMERIC_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
        else:
            out[column] = 0
    out["stock_sort_order"] = out["stock_sort_order"].astype(int)
    if out["stock_label"].str.strip().eq("").all():
        out["stock_label"] = out["stock_name_cn"].where(out["stock_name_cn"].str.strip() != "", out["stock_id"])
    out = out.sort_values(["month_order", "stock_sort_order", "stock_id"], kind="stable")
    return out.reset_index(drop=True)


def _prepare_metadata(value: object) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        return pd.DataFrame()
    out = value.copy()
    for column in ("stock_id", "stock_key", "stock_name_cn", "stock_label", "country_group"):
        if column in out.columns:
            out[column] = out[column].fillna("").astype(str)
    if "stock_sort_order" in out.columns:
        out["stock_sort_order"] = pd.to_numeric(out["stock_sort_order"], errors="coerce").fillna(999).astype(int)
    else:
        out["stock_sort_order"] = 999
    return out.sort_values(["stock_sort_order", "stock_id"], kind="stable").reset_index(drop=True)


def month_options(df: pd.DataFrame) -> list[str]:
    if "month_label" not in df.columns:
        return []
    values = df["month_label"].dropna().astype(str)
    months = {value for value in values if value.strip() and value.strip().lower() != "nan"}
    return sorted(months, key=month_sort_key)


def filter_month_range(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if "month_label" not in df.columns:
        return df
    start_key = month_sort_key(start)
    end_key = month_sort_key(end)
    if start_key > end_key:
        start_key, end_key = end_key, start_key
    keys = df["month_label"].fillna("").astype(str).map(month_sort_key)
    return df[keys.between(start_key, end_key, inclusive="both")]


def month_sort_key(value: object) -> int:
    text = str(value or "").strip().replace("/", "-").replace(".", "-")
    parts = text.split("-")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        year = int(parts[0])
        month = int(parts[1])
        if 1 <= month <= 12:
            return year * 100 + month
    return 999999


def summary_metrics(df: pd.DataFrame) -> dict[str, Any]:
    latest = latest_month(df)
    latest_rows = df[df["month_label"].astype(str) == latest] if latest != "-" else df.iloc[0:0]
    return {
        "stock_count": int(df["stock_id"].nunique()) if "stock_id" in df.columns and not df.empty else 0,
        "latest_month": latest,
        "latest_active_merchants": sum_number(latest_rows, "redeeming_submerchant_count"),
        "latest_redeemed_coupons": sum_number(latest_rows, "redeemed_coupon_code_count_trade"),
        "latest_cost": sum_number(latest_rows, "cost_money_yuan"),
    }


def latest_month(df: pd.DataFrame) -> str:
    months = month_options(df)
    return months[-1] if months else "-"


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["month_label", *NUMERIC_COLUMNS])
    grouped = df.groupby("month_label", dropna=False).agg(
        redeeming_submerchant_count=("redeeming_submerchant_count", "sum"),
        redeemed_coupon_code_count_trade=("redeemed_coupon_code_count_trade", "sum"),
        used_coupon_code_count_stock_dim=("used_coupon_code_count_stock_dim", "sum"),
        issued_coupon_code_count=("issued_coupon_code_count", "sum"),
        trade_order_count=("trade_order_count", "sum"),
        pay_amt_cny_yuan=("pay_amt_cny_yuan", "sum"),
        user_save_money_yuan=("user_save_money_yuan", "sum"),
        cost_money_yuan=("cost_money_yuan", "sum"),
    )
    out = grouped.reset_index()
    out["month_order"] = out["month_label"].map(month_sort_key)
    return out.sort_values("month_order").drop(columns="month_order").reset_index(drop=True)


def stock_totals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    grouped = df.groupby(
        ["country_group", "stock_id", "stock_key", "stock_label", "stock_sort_order"],
        dropna=False,
    ).agg(
        first_month=("month_label", _first_month),
        latest_month=("month_label", _latest_month),
        month_count=("month_label", "nunique"),
        total_issued_coupon_code_count=("issued_coupon_code_count", "sum"),
        total_used_coupon_code_count_stock_dim=("used_coupon_code_count_stock_dim", "sum"),
        total_redeemed_coupon_code_count_trade=("redeemed_coupon_code_count_trade", "sum"),
        active_merchant_month_sum=("redeeming_submerchant_count", "sum"),
        max_monthly_redeeming_submerchant_count=("redeeming_submerchant_count", "max"),
        total_trade_order_count=("trade_order_count", "sum"),
        total_pay_amt_cny_yuan=("pay_amt_cny_yuan", "sum"),
        total_user_save_money_yuan=("user_save_money_yuan", "sum"),
        total_cost_money_yuan=("cost_money_yuan", "sum"),
    )
    out = grouped.reset_index()
    out["redeemed_per_active_merchant"] = _safe_ratio(
        out["total_redeemed_coupon_code_count_trade"],
        out["active_merchant_month_sum"],
    )
    out["cost_per_redeemed_coupon_yuan"] = _safe_ratio(
        out["total_cost_money_yuan"],
        out["total_redeemed_coupon_code_count_trade"],
    )
    return out.sort_values(["stock_sort_order", "stock_id"], kind="stable").reset_index(drop=True)


def stock_label_map(df: pd.DataFrame) -> dict[str, str]:
    if df.empty or "stock_id" not in df.columns:
        return {}
    labels: dict[str, str] = {}
    ordered = df.copy()
    if "stock_sort_order" in ordered.columns:
        ordered = ordered.sort_values(["stock_sort_order", "stock_id"], kind="stable")
    for row in ordered.to_dict("records"):
        stock_id = str(row.get("stock_id") or "").strip()
        if not stock_id or stock_id in labels:
            continue
        label = str(row.get("stock_label") or row.get("stock_name_cn") or stock_id).strip()
        labels[stock_id] = label or stock_id
    return labels


def line_option(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    title: str,
    series_name: str,
    color: str,
) -> dict[str, Any]:
    rows = df.to_dict("records")
    return _base_option(title) | {
        "xAxis": _category_axis([_json_value(row.get(x)) for row in rows]),
        "yAxis": _value_axis(series_name),
        "series": [
            {
                "name": series_name,
                "type": "line",
                "smooth": True,
                "symbolSize": 7,
                "lineStyle": {"width": 4, "color": color},
                "itemStyle": {"color": color, "borderColor": PALETTE["white"], "borderWidth": 2},
                "areaStyle": {"opacity": 0.08, "color": color},
                "data": [_json_value(row.get(y)) for row in rows],
            }
        ],
    }


def stacked_stock_option(df: pd.DataFrame, *, metric: str, title: str) -> dict[str, Any]:
    months = month_options(df)
    stocks = (
        df[["stock_id", "stock_label", "stock_sort_order"]]
        .drop_duplicates("stock_id")
        .sort_values(["stock_sort_order", "stock_id"], kind="stable")
        .to_dict("records")
    )
    series = []
    for stock in stocks:
        stock_id = str(stock["stock_id"])
        stock_rows = df[df["stock_id"].astype(str) == stock_id]
        month_values = stock_rows.groupby("month_label", dropna=False)[metric].sum().to_dict()
        series.append(
            {
                "name": str(stock.get("stock_label") or stock_id),
                "type": "bar",
                "stack": "total",
                "barMaxWidth": 26,
                "emphasis": {"focus": "series"},
                "data": [_json_value(month_values.get(month, 0)) for month in months],
            }
        )
    return _base_option(title) | {
        "legend": {"top": 8, "right": 12, "textStyle": {"color": "#5c6c75"}},
        "xAxis": _category_axis(months, rotate=35),
        "yAxis": _value_axis(METRIC_LABELS.get(metric, metric)),
        "series": series,
    }


def _base_option(title: str) -> dict[str, Any]:
    return {
        "backgroundColor": "transparent",
        "color": [
            PALETTE["green"],
            PALETTE["blue"],
            PALETTE["cyan"],
            PALETTE["dark_green"],
            PALETTE["deep_teal"],
            PALETTE["hover_blue"],
            PALETTE["teal_gray"],
        ],
        "title": {
            "text": title,
            "left": 4,
            "top": 2,
            "textStyle": {"color": "#001e2b", "fontSize": 15, "fontWeight": 600},
        },
        "tooltip": {
            "trigger": "axis",
            "confine": True,
            "backgroundColor": PALETTE["forest"],
            "borderColor": PALETTE["teal_gray"],
            "textStyle": {"color": PALETTE["white"]},
        },
        "grid": {"left": 72, "right": 42, "top": 62, "bottom": 54},
    }


def _category_axis(data: list[Any], rotate: int = 0) -> dict[str, Any]:
    return {
        "type": "category",
        "data": data,
        "axisLabel": {"color": "#5c6c75", "rotate": rotate},
        "axisLine": {"lineStyle": {"color": "#b8c4c2"}},
        "axisTick": {"show": False},
    }


def _value_axis(name: str) -> dict[str, Any]:
    return {
        "type": "value",
        "name": name,
        "nameTextStyle": {"color": "#5c6c75"},
        "axisLabel": {"color": "#5c6c75"},
        "axisLine": {"lineStyle": {"color": "#b8c4c2"}},
        "splitLine": {"lineStyle": {"color": "#d8e1df"}},
    }


def _first_month(values: pd.Series) -> str:
    months = sorted((str(value) for value in values if str(value).strip()), key=month_sort_key)
    return months[0] if months else ""


def _latest_month(values: pd.Series) -> str:
    months = sorted((str(value) for value in values if str(value).strip()), key=month_sort_key)
    return months[-1] if months else ""


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    top = pd.to_numeric(numerator, errors="coerce").fillna(0)
    bottom = pd.to_numeric(denominator, errors="coerce").fillna(0)
    return top.divide(bottom.mask(bottom.eq(0))).fillna(0).round(4)


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return ""
    if hasattr(value, "item"):
        return value.item()
    return value


def _select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[[column for column in columns if column in df.columns]]
