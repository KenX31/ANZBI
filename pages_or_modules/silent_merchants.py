from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd
import streamlit as st

from auth import can_export_data, render_export_restricted_notice
from charts import (
    PALETTE,
    donut_option,
    empty_chart,
    horizontal_bar_option,
    render_echart,
    simple_bar_option,
    treemap_option,
)
from exports import (
    SILENT_ACCESS_AGE_LABELS,
    SILENT_BUSINESS_TYPE_LABELS,
    SILENT_COUNTRY_LABELS,
    SILENT_TIER_LABELS,
    csv_bytes,
    silent_merchants_internal_export,
    silent_merchants_provider_export,
)
from filters import (
    apply_in_filter,
    apply_text_filter,
    disabled_multiselect_filter,
    mapped_multiselect_filter,
    multiselect_filter,
    options,
)
from geography import GeoFilterSpec, country_scope, with_reporting_geography
from metrics import format_int, format_pct, rate


ADDRESS_SCOPE_LABELS = {
    "全部": "all",
    "有地址": "has_address",
    "缺少地址": "missing_address",
}
SILENCE_TIER_ORDER = ["new_unactivated_180d", "initial_silent", "deep_silent"]
ACCESS_AGE_ORDER = ["access_180_359d", "access_gte_360d"]


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


def render_silent_merchants_page(data: dict[str, object]) -> None:
    query = data.get("query")
    if query is not None:
        rows = _prepare_rows(query.filter_frame().copy())  # type: ignore[union-attr]
    else:
        rows = _prepare_rows(data["rows"].copy())  # type: ignore[index, union-attr]
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    if rows.empty:
        st.warning("没有可用的沉默商户数据。")
        return

    st.header("沉默商户")
    st.caption(
        "当前快照日期为 2026-05-01。v1 口径保留澳大利亚/新西兰线下或线上+线下商户，"
        "排除振兴机构，要求商户接入已满 180 天，并且最近 180 天交易笔数为 0。"
    )
    _sample_notice(summary, rows)

    if query is not None:
        filtered = _sidebar_filters_query(query, rows)  # type: ignore[arg-type]
    else:
        filtered = _sidebar_filters(rows)
    total = len(filtered)
    new_unactivated = _tier_count(filtered, "new_unactivated_180d")
    initial_silent = _tier_count(filtered, "initial_silent")
    deep_silent = _tier_count(filtered, "deep_silent")
    address_count = int(_has_address_series(filtered).sum()) if total else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("候选商户", format_int(total))
    c2.metric("新接入180天未激活", format_int(new_unactivated))
    c3.metric("初始沉默", format_int(initial_silent))
    c4.metric("深度沉默", format_int(deep_silent))
    c5.metric("地址覆盖率", format_pct(rate(address_count, total)))

    if filtered.empty:
        st.info("当前筛选下没有匹配商户。")
        return

    if can_export_data():
        provider_export = silent_merchants_provider_export(filtered)
        internal_export = silent_merchants_internal_export(filtered)
        d1, d2 = st.columns(2)
        d1.download_button(
            "导出服务商执行清单",
            csv_bytes(provider_export),
            "silent_merchants_provider_execution_list.csv",
            "text/csv",
        )
        d2.download_button(
            "导出内部记录清单",
            csv_bytes(internal_export),
            "silent_merchants_internal_record_list.csv",
            "text/csv",
        )
    else:
        render_export_restricted_notice()

    tab_overview, tab_area, tab_institutions, tab_merchants = st.tabs(
        ["总览", "区域", "机构", "商户明细"]
    )
    with tab_overview:
        c1, c2 = st.columns(2)
        with c1:
            tier = _distribution(filtered, "silence_tier", value_map=SILENT_TIER_LABELS, order=SILENCE_TIER_ORDER)
            render_echart(
                donut_option(tier, label="label", value="count", title="沉默分层"),
                key="chart_silent_tier",
                height=330,
            )
        with c2:
            country = _distribution(filtered, "geo_country", value_map=SILENT_COUNTRY_LABELS)
            render_echart(
                donut_option(country, label="label", value="count", title="国家分布"),
                key="chart_silent_country",
                height=330,
            )

        c1, c2 = st.columns(2)
        with c1:
            access = _distribution(filtered, "access_age_band", value_map=SILENT_ACCESS_AGE_LABELS, order=ACCESS_AGE_ORDER)
            render_echart(
                simple_bar_option(access, x="label", y="count", title="接入时长分布", color=PALETTE["cyan"]),
                key="chart_silent_access_age",
                height=330,
            )
        with c2:
            business = _distribution(filtered, "business_type", value_map=SILENT_BUSINESS_TYPE_LABELS)
            render_echart(
                simple_bar_option(business, x="label", y="count", title="业务类型分布", color=PALETTE["green"]),
                key="chart_silent_business_type",
                height=330,
            )

    with tab_area:
        area = _area_rollup(filtered)
        if area.empty:
            empty_chart("当前筛选下没有可用区域数据。")
        else:
            render_echart(
                horizontal_bar_option(
                    area.head(20),
                    label="geo_reporting_name",
                    value="merchant_count",
                    title="沉默商户区域排名",
                    color=PALETTE["blue"],
                ),
                key="chart_silent_area_rank",
                height=560,
            )
            st.dataframe(_display_table(area), use_container_width=True, hide_index=True)

    with tab_institutions:
        institutions = _institution_rollup(filtered)
        render_echart(
            horizontal_bar_option(
                institutions.head(20),
                label="institution_name",
                value="merchant_count",
                title="机构排名",
                color=PALETTE["cyan"],
            ),
            key="chart_silent_institution_rank",
            height=520,
        )
        tier_mix = _institution_tier_treemap(institutions).head(14)
        render_echart(
            treemap_option(
                tier_mix,
                label="label",
                value="merchant_count",
                title="机构集中度",
            ),
            key="chart_silent_institution_treemap",
            height=360,
        )
        st.dataframe(_display_table(institutions), use_container_width=True, hide_index=True)

    with tab_merchants:
        display = _select_columns(
            filtered,
            [
                "merchant_id",
                "merchant_display_name",
                "institution_name",
                "institution_group",
                "geo_country",
                "geo_state",
                "geo_city",
                "geo_suburb",
                "geo_postcode",
                "geo_reporting_name",
                "nz_geo_area",
                "silence_tier",
                "access_age_band",
                "merchant_access_time",
                "business_type",
                "mcc_code",
                "txn_count_360d",
                "txn_amount_360d",
                "address",
            ],
        )
        st.dataframe(_display_table(display), use_container_width=True, hide_index=True)


def _prepare_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "address" not in out.columns and "stores_address" in out.columns:
        out["address"] = out["stores_address"]
    out = _normalize_numeric(out)
    return with_reporting_geography(out, country_columns=["country_group", "merchant_country_code"])


def _sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader("沉默商户筛选")
    filtered = df

    selected_country = mapped_multiselect_filter(
        "国家", filtered, "geo_country", key="silent_country", value_map=SILENT_COUNTRY_LABELS
    )
    if selected_country:
        filtered = apply_in_filter(filtered, "geo_country", selected_country)

    filtered = _apply_geo_filters(filtered)

    selected_tier = mapped_multiselect_filter(
        "沉默分层", filtered, "silence_tier", key="silent_tier", value_map=SILENT_TIER_LABELS
    )
    if selected_tier:
        filtered = apply_in_filter(filtered, "silence_tier", selected_tier)

    selected_age = mapped_multiselect_filter(
        "接入时长", filtered, "access_age_band", key="silent_age", value_map=SILENT_ACCESS_AGE_LABELS
    )
    if selected_age:
        filtered = apply_in_filter(filtered, "access_age_band", selected_age)

    selected_business_type = mapped_multiselect_filter(
        "业务类型", filtered, "business_type", key="silent_business_type", value_map=SILENT_BUSINESS_TYPE_LABELS
    )
    if selected_business_type:
        filtered = apply_in_filter(filtered, "business_type", selected_business_type)

    for label, column, key in (
        ("机构分组", "institution_group", "silent_institution_group"),
        ("机构", "institution_name", "silent_institution"),
        ("MCC代码", "mcc_code", "silent_mcc_code"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = apply_in_filter(filtered, column, selected)

    address_scope = st.sidebar.selectbox("地址可用性", list(ADDRESS_SCOPE_LABELS), key="silent_address_scope")
    filtered = _filter_address_scope(filtered, ADDRESS_SCOPE_LABELS[address_scope])

    bounds = _access_date_bounds(filtered)
    if bounds:
        value = st.sidebar.date_input(
            "接入日期范围",
            value=(bounds.start, bounds.end),
            min_value=bounds.start,
            max_value=bounds.end,
            key="silent_access_date_range",
        )
        if isinstance(value, tuple) and len(value) == 2:
            filtered = _filter_access_date_range(filtered, value[0], value[1])

    query = st.sidebar.text_input("商户/机构/区域/ID关键词", key="silent_query")
    return apply_text_filter(
        filtered,
        [
            "merchant_id",
            "merchant_display_name",
            "merchant_company_name",
            "merchant_short_name",
            "institution_id",
            "institution_name",
            "institution_group",
            "geo_reporting_name",
            "geo_city",
            "geo_suburb",
            "address",
            "stores_address",
            "mcc_code",
        ],
        query,
    )


def _sidebar_filters_query(query: object, option_rows: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.subheader("沉默商户筛选")
    filtered = option_rows
    criteria: dict[str, object] = {"in_filters": {}, "residual_in_filters": {}}

    selected_country = mapped_multiselect_filter(
        "国家", filtered, "geo_country", key="silent_country", value_map=SILENT_COUNTRY_LABELS
    )
    filtered = _apply_query_in_filter(filtered, criteria, "geo_country", selected_country)

    filtered = _apply_geo_filters_query(filtered, criteria)

    selected_tier = mapped_multiselect_filter(
        "沉默分层", filtered, "silence_tier", key="silent_tier", value_map=SILENT_TIER_LABELS
    )
    filtered = _apply_query_in_filter(filtered, criteria, "silence_tier", selected_tier)

    selected_age = mapped_multiselect_filter(
        "接入时长", filtered, "access_age_band", key="silent_age", value_map=SILENT_ACCESS_AGE_LABELS
    )
    filtered = _apply_query_in_filter(filtered, criteria, "access_age_band", selected_age)

    selected_business_type = mapped_multiselect_filter(
        "业务类型", filtered, "business_type", key="silent_business_type", value_map=SILENT_BUSINESS_TYPE_LABELS
    )
    filtered = _apply_query_in_filter(filtered, criteria, "business_type", selected_business_type)

    for label, column, key in (
        ("机构分组", "institution_group", "silent_institution_group"),
        ("机构", "institution_name", "silent_institution"),
        ("MCC代码", "mcc_code", "silent_mcc_code"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        filtered = _apply_query_in_filter(filtered, criteria, column, selected)

    address_scope = st.sidebar.selectbox("地址可用性", list(ADDRESS_SCOPE_LABELS), key="silent_address_scope")
    criteria["address_scope"] = ADDRESS_SCOPE_LABELS[address_scope]
    filtered = _filter_address_scope(filtered, ADDRESS_SCOPE_LABELS[address_scope])

    bounds = _access_date_bounds(filtered)
    if bounds:
        value = st.sidebar.date_input(
            "接入日期范围",
            value=(bounds.start, bounds.end),
            min_value=bounds.start,
            max_value=bounds.end,
            key="silent_access_date_range",
        )
        if isinstance(value, tuple) and len(value) == 2:
            criteria["access_date_range"] = [value[0].isoformat(), value[1].isoformat()]
            filtered = _filter_access_date_range(filtered, value[0], value[1])

    criteria["text_query"] = st.sidebar.text_input("商户/机构/区域/ID关键词", key="silent_query")
    rows = _prepare_rows(query.rows(criteria))  # type: ignore[attr-defined]
    return _apply_silent_residual_filters(rows, criteria)


def _apply_geo_filters(df: pd.DataFrame) -> pd.DataFrame:
    scope = country_scope(df)
    if scope == "NZ":
        return _apply_nz_geo_filters(df)
    if scope == "MIXED":
        selected_city = multiselect_filter("城市", df, "geo_city", key="silent_geo_city")
        filtered = apply_in_filter(df, "geo_city", selected_city) if selected_city else df
        if selected_city and country_scope(filtered) == "NZ":
            return _apply_nz_geo_filters(filtered, selected_city=selected_city)
        if selected_city and country_scope(filtered) == "AU":
            return _apply_standard_geo_filters(filtered, skip_columns={"geo_city"})
        return filtered
    return _apply_standard_geo_filters(df)


def _apply_geo_filters_query(df: pd.DataFrame, criteria: dict[str, object]) -> pd.DataFrame:
    scope = country_scope(df)
    if scope == "NZ":
        return _apply_nz_geo_filters_query(df, criteria)
    if scope == "MIXED":
        selected_city = multiselect_filter("城市", df, "geo_city", key="silent_geo_city")
        filtered = _apply_query_in_filter(df, criteria, "geo_city", selected_city)
        if selected_city and country_scope(filtered) == "NZ":
            return _apply_nz_geo_filters_query(filtered, criteria, selected_city=selected_city)
        if selected_city and country_scope(filtered) == "AU":
            return _apply_standard_geo_filters_query(filtered, criteria, skip_columns={"geo_city"})
        return filtered
    return _apply_standard_geo_filters_query(df, criteria)


def _apply_nz_geo_filters(df: pd.DataFrame, *, selected_city: list[str] | None = None) -> pd.DataFrame:
    filtered = df
    if selected_city is None:
        selected_city = multiselect_filter("城市", filtered, "geo_city", key="silent_geo_city")
        if selected_city:
            filtered = apply_in_filter(filtered, "geo_city", selected_city)

    area_key = "silent_nz_geo_area"
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
        ("NZ 商圈集群", "nz_business_cluster", "silent_nz_cluster"),
        ("街区", "geo_suburb", "silent_geo_suburb"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = apply_in_filter(filtered, column, selected)
    return filtered


def _apply_nz_geo_filters_query(
    df: pd.DataFrame,
    criteria: dict[str, object],
    *,
    selected_city: list[str] | None = None,
) -> pd.DataFrame:
    filtered = df
    if selected_city is None:
        selected_city = multiselect_filter("城市", filtered, "geo_city", key="silent_geo_city")
        filtered = _apply_query_in_filter(filtered, criteria, "geo_city", selected_city)

    area_key = "silent_nz_geo_area"
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
        filtered = _apply_query_in_filter(filtered, criteria, "nz_geo_area", selected_area)

    for label, column, key in (
        ("NZ 商圈集群", "nz_business_cluster", "silent_nz_cluster"),
        ("街区", "geo_suburb", "silent_geo_suburb"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        filtered = _apply_query_in_filter(filtered, criteria, column, selected)
    return filtered


def _apply_standard_geo_filters(df: pd.DataFrame, *, skip_columns: set[str] | None = None) -> pd.DataFrame:
    filtered = df
    skip_columns = skip_columns or set()
    for spec in _geo_filter_specs(country_scope(filtered)):
        if spec.column in skip_columns:
            continue
        selected = multiselect_filter(spec.label, filtered, spec.column, key=f"silent_{spec.key_suffix}")
        if selected:
            filtered = apply_in_filter(filtered, spec.column, selected)
    return filtered


def _apply_standard_geo_filters_query(
    df: pd.DataFrame,
    criteria: dict[str, object],
    *,
    skip_columns: set[str] | None = None,
) -> pd.DataFrame:
    filtered = df
    skip_columns = skip_columns or set()
    for spec in _geo_filter_specs(country_scope(filtered)):
        if spec.column in skip_columns:
            continue
        selected = multiselect_filter(spec.label, filtered, spec.column, key=f"silent_{spec.key_suffix}")
        filtered = _apply_query_in_filter(filtered, criteria, spec.column, selected)
    return filtered


def _apply_query_in_filter(
    df: pd.DataFrame,
    criteria: dict[str, object],
    column: str,
    selected: list[str],
) -> pd.DataFrame:
    if not selected:
        return df
    filters = criteria.setdefault("in_filters", {})
    if isinstance(filters, dict):
        filters[column] = [str(value) for value in selected]
    return apply_in_filter(df, column, selected)


def _apply_silent_residual_filters(df: pd.DataFrame, criteria: dict[str, object]) -> pd.DataFrame:
    filtered = df
    filters = criteria.get("in_filters") if isinstance(criteria.get("in_filters"), dict) else {}
    for column, selected in filters.items():
        if isinstance(selected, list):
            filtered = apply_in_filter(filtered, column, selected)

    address_scope = str(criteria.get("address_scope") or "all")
    filtered = _filter_address_scope(filtered, address_scope)

    access_date_range = criteria.get("access_date_range")
    if isinstance(access_date_range, list) and len(access_date_range) == 2:
        start = pd.to_datetime(access_date_range[0], errors="coerce")
        end = pd.to_datetime(access_date_range[1], errors="coerce")
        if pd.notna(start) and pd.notna(end):
            filtered = _filter_access_date_range(filtered, start.date(), end.date())

    return apply_text_filter(
        filtered,
        [
            "merchant_id",
            "merchant_display_name",
            "merchant_company_name",
            "merchant_short_name",
            "institution_id",
            "institution_name",
            "institution_group",
            "geo_reporting_name",
            "geo_city",
            "geo_suburb",
            "address",
            "stores_address",
            "mcc_code",
        ],
        str(criteria.get("text_query") or ""),
    )


def _geo_filter_specs(scope: str) -> list[GeoFilterSpec]:
    if scope == "NZ":
        return [
            GeoFilterSpec("城市", "geo_city", "geo_city"),
            GeoFilterSpec("NZ 地理片区", "nz_geo_area", "nz_geo_area"),
            GeoFilterSpec("NZ 商圈集群", "nz_business_cluster", "nz_cluster"),
            GeoFilterSpec("街区", "geo_suburb", "geo_suburb"),
        ]
    if scope == "AU":
        return [
            GeoFilterSpec("州/省", "geo_state", "geo_state"),
            GeoFilterSpec("城市", "geo_city", "geo_city"),
            GeoFilterSpec("街区", "geo_suburb", "geo_suburb"),
            GeoFilterSpec("邮编", "geo_postcode", "geo_postcode"),
        ]
    return [GeoFilterSpec("城市", "geo_city", "geo_city")]


def _normalize_numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in (
        "txn_count_30d",
        "txn_amount_30d",
        "txn_count_180d",
        "txn_amount_180d",
        "txn_count_360d",
        "txn_amount_360d",
        "txn_count_720d",
        "txn_amount_720d",
        "has_address_flag",
        "field_visit_priority_scope_flag",
    ):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0)
    return out


def _filter_access_date_range(df: pd.DataFrame, start: date | None, end: date | None) -> pd.DataFrame:
    if start is None or end is None or "merchant_access_time" not in df.columns:
        return df
    parsed = _access_datetimes(df)
    if parsed.isna().all():
        return df
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    if start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts
    mask = parsed.between(start_ts, end_ts, inclusive="both")
    return df[mask.fillna(False)]


def _access_date_bounds(df: pd.DataFrame) -> DateRange | None:
    if "merchant_access_time" not in df.columns or df.empty:
        return None
    parsed = _access_datetimes(df).dropna()
    if parsed.empty:
        return None
    return DateRange(parsed.min().date(), parsed.max().date())


def _access_datetimes(df: pd.DataFrame) -> pd.Series:
    values = df["merchant_access_time"].fillna("").astype(str).str.replace("\u00a0", " ", regex=False)
    return pd.to_datetime(values, errors="coerce")


def _filter_address_scope(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == "all":
        return df
    has_address = _has_address_series(df)
    if scope == "has_address":
        return df[has_address]
    if scope == "missing_address":
        return df[~has_address]
    return df


def _has_address_series(df: pd.DataFrame) -> pd.Series:
    if "has_address_flag" in df.columns:
        values = pd.to_numeric(df["has_address_flag"], errors="coerce").fillna(0)
        return values > 0
    address_columns = [column for column in ("address", "stores_address") if column in df.columns]
    if not address_columns:
        return pd.Series(False, index=df.index)
    result = pd.Series(False, index=df.index)
    for column in address_columns:
        text = df[column].fillna("").astype(str).str.strip()
        result = result | ~text.str.casefold().isin({"", "nan", "none", "null"})
    return result


def _tier_count(df: pd.DataFrame, tier: str) -> int:
    if "silence_tier" not in df.columns:
        return 0
    return int((df["silence_tier"].astype(str) == tier).sum())


def _distribution(
    df: pd.DataFrame,
    column: str,
    *,
    value_map: dict[str, str] | None = None,
    order: Iterable[str] | None = None,
) -> pd.DataFrame:
    if column not in df.columns:
        return pd.DataFrame(columns=["label", "count"])
    out = df[column].fillna("UNKNOWN").astype(str).value_counts().rename_axis("value").reset_index(name="count")
    if order:
        order_map = {value: index for index, value in enumerate(order)}
        out["_order"] = out["value"].map(lambda value: order_map.get(value, len(order_map)))
        out = out.sort_values(["_order", "value"]).drop(columns="_order")
    if value_map:
        out["label"] = out["value"].map(lambda value: value_map.get(value, value or "未分类"))
    else:
        out["label"] = out["value"].replace({"UNKNOWN": "未分类", "": "未分类"})
    return out[["label", "count"]]


def _area_rollup(df: pd.DataFrame) -> pd.DataFrame:
    if "geo_reporting_name" not in df.columns:
        return pd.DataFrame()
    working = df.copy()
    working["geo_reporting_name"] = working["geo_reporting_name"].fillna("").astype(str).str.strip()
    working.loc[working["geo_reporting_name"] == "", "geo_reporting_name"] = "未匹配"
    grouped = working.groupby(["geo_country", "geo_reporting_level", "geo_reporting_name"], dropna=False).agg(
        merchant_count=("merchant_id", "count"),
        new_unactivated_180d=("silence_tier", lambda s: (s.astype(str) == "new_unactivated_180d").sum()),
        initial_silent=("silence_tier", lambda s: (s.astype(str) == "initial_silent").sum()),
        deep_silent=("silence_tier", lambda s: (s.astype(str) == "deep_silent").sum()),
        address_count=("has_address_flag", lambda s: (pd.to_numeric(s, errors="coerce").fillna(0) > 0).sum()),
    )
    out = grouped.reset_index().sort_values(["merchant_count", "geo_reporting_name"], ascending=[False, True])
    out["geo_reporting_level_label"] = out["geo_reporting_level"].map(_geo_level_label_en)
    out["address_coverage"] = out["address_count"] / out["merchant_count"].replace(0, pd.NA)
    return out


def _institution_rollup(df: pd.DataFrame) -> pd.DataFrame:
    if "institution_name" not in df.columns:
        return pd.DataFrame()
    working = df.copy()
    working["institution_name"] = working["institution_name"].fillna("").astype(str).str.strip()
    working.loc[working["institution_name"] == "", "institution_name"] = "未知机构"
    grouped = working.groupby(["institution_group", "institution_name"], dropna=False).agg(
        merchant_count=("merchant_id", "count"),
        new_unactivated_180d=("silence_tier", lambda s: (s.astype(str) == "new_unactivated_180d").sum()),
        initial_silent=("silence_tier", lambda s: (s.astype(str) == "initial_silent").sum()),
        deep_silent=("silence_tier", lambda s: (s.astype(str) == "deep_silent").sum()),
        address_count=("has_address_flag", lambda s: (pd.to_numeric(s, errors="coerce").fillna(0) > 0).sum()),
    )
    out = grouped.reset_index().sort_values(["merchant_count", "institution_name"], ascending=[False, True])
    out["address_coverage"] = out["address_count"] / out["merchant_count"].replace(0, pd.NA)
    return out


def _institution_tier_treemap(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["label", "merchant_count"])
    out = df[["institution_name", "merchant_count"]].copy()
    out["label"] = out["institution_name"]
    return out.sort_values("merchant_count", ascending=False)


def _geo_level_label_en(value: object) -> str:
    mapping = {
        "nz_geo_area": "NZ 地理片区",
        "nz_cluster": "NZ 商圈集群",
        "au_service_area": "AU 服务区域",
        "au_city": "AU 城市",
        "au_state": "AU 州/省",
        "au_suburb": "AU 街区",
        "city": "城市",
        "suburb": "街区",
        "postcode": "邮编",
        "country": "国家",
        "unmatched": "未匹配",
    }
    return mapping.get(str(value or ""), str(value or ""))


def _display_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "geo_country" in out.columns:
        out["geo_country"] = out["geo_country"].map(lambda value: SILENT_COUNTRY_LABELS.get(str(value), value))
    if "silence_tier" in out.columns:
        out["silence_tier"] = out["silence_tier"].map(lambda value: SILENT_TIER_LABELS.get(str(value), value))
    if "access_age_band" in out.columns:
        out["access_age_band"] = out["access_age_band"].map(lambda value: SILENT_ACCESS_AGE_LABELS.get(str(value), value))
    if "business_type" in out.columns:
        out["business_type"] = out["business_type"].map(lambda value: SILENT_BUSINESS_TYPE_LABELS.get(str(value), value))
    if "address_coverage" in out.columns:
        out["address_coverage"] = out["address_coverage"].map(_format_rate_value)
    return out.rename(columns={key: value for key, value in _COLUMN_LABELS.items() if key in out.columns})


def _select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[[column for column in columns if column in df.columns]]


def _sample_notice(summary: object, rows: pd.DataFrame) -> None:
    if not isinstance(summary, dict):
        return
    aggregate_count = int(float(summary.get("aggregate_merchant_count") or 0))
    detail_count = int(float(summary.get("detail_row_count") or len(rows)))
    if aggregate_count and detail_count and detail_count < aggregate_count:
        st.info(
            f"当前加载的明细行为抽样数据（{detail_count:,} / {aggregate_count:,} 个汇总商户）。"
            "图表、筛选器和导出均基于已加载明细行。"
        )


def _format_rate_value(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0]
    return format_pct(float(numeric))


_COLUMN_LABELS = {
    "merchant_id": "商户MID",
    "merchant_display_name": "商户名称",
    "institution_group": "机构分组",
    "institution_name": "机构",
    "geo_country": "国家",
    "geo_state": "州/省",
    "geo_city": "城市",
    "geo_suburb": "街区",
    "geo_postcode": "邮编",
    "geo_reporting_level": "地理层级代码",
    "geo_reporting_level_label": "地理层级",
    "geo_reporting_name": "地理展示名称",
    "nz_geo_area": "NZ 地理片区",
    "silence_tier": "沉默分层",
    "access_age_band": "接入时长",
    "merchant_access_time": "接入时间",
    "business_type": "业务类型",
    "mcc_code": "MCC代码",
    "txn_count_360d": "近360天交易笔数",
    "txn_amount_360d": "近360天交易金额",
    "address": "地址",
    "merchant_count": "商户数",
    "new_unactivated_180d": "新接入180天未激活",
    "initial_silent": "初始沉默",
    "deep_silent": "深度沉默",
    "address_count": "有地址商户数",
    "address_coverage": "地址覆盖率",
}
