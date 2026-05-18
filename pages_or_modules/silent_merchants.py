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
    SILENT_TIER_LABELS,
    csv_bytes,
    silent_merchants_internal_export,
    silent_merchants_provider_export,
)
from filters import apply_text_filter, disabled_multiselect_filter, mapped_multiselect_filter, multiselect_filter, options
from geography import GeoFilterSpec, country_scope, with_reporting_geography
from metrics import format_int, format_pct, rate


COUNTRY_LABELS_EN = {
    "AU": "Australia",
    "NZ": "New Zealand",
}
ADDRESS_SCOPE_LABELS = {
    "All": "all",
    "Has address": "has_address",
    "Missing address": "missing_address",
}
SILENCE_TIER_ORDER = ["new_unactivated_180d", "initial_silent", "deep_silent"]
ACCESS_AGE_ORDER = ["access_180_359d", "access_gte_360d"]


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


def render_silent_merchants_page(data: dict[str, object]) -> None:
    rows = _prepare_rows(data["rows"].copy())  # type: ignore[index, union-attr]
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    if rows.empty:
        st.warning("No silent merchant data is available.")
        return

    st.header("Silent Merchants")
    st.caption(
        "Activation opportunity pool as of snapshot 2026-05-01. The v1 scope keeps AU/NZ OFFLINE or BOTH "
        "merchants, excludes Zhenxing institutions, requires at least 180 days since access, and keeps only "
        "merchants with zero transactions in the latest 180-day window."
    )
    _sample_notice(summary, rows)

    filtered = _sidebar_filters(rows)
    total = len(filtered)
    new_unactivated = _tier_count(filtered, "new_unactivated_180d")
    initial_silent = _tier_count(filtered, "initial_silent")
    deep_silent = _tier_count(filtered, "deep_silent")
    address_count = int(_has_address_series(filtered).sum()) if total else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Candidate merchants", format_int(total))
    c2.metric("New unactivated 180d", format_int(new_unactivated))
    c3.metric("Initial silent", format_int(initial_silent))
    c4.metric("Deep silent", format_int(deep_silent))
    c5.metric("Address coverage", format_pct(rate(address_count, total)))

    if filtered.empty:
        st.info("No merchants match the current filters.")
        return

    if can_export_data():
        provider_export = silent_merchants_provider_export(filtered)
        internal_export = silent_merchants_internal_export(filtered)
        d1, d2 = st.columns(2)
        d1.download_button(
            "Export provider execution list",
            csv_bytes(provider_export),
            "silent_merchants_provider_execution_list.csv",
            "text/csv",
        )
        d2.download_button(
            "Export internal record list",
            csv_bytes(internal_export),
            "silent_merchants_internal_record_list.csv",
            "text/csv",
        )
    else:
        render_export_restricted_notice()

    tab_overview, tab_area, tab_institutions, tab_merchants = st.tabs(
        ["Overview", "Area", "Institutions", "Merchant Details"]
    )
    with tab_overview:
        c1, c2 = st.columns(2)
        with c1:
            tier = _distribution(filtered, "silence_tier", value_map=SILENT_TIER_LABELS, order=SILENCE_TIER_ORDER)
            render_echart(
                donut_option(tier, label="label", value="count", title="Silence tier"),
                key="chart_silent_tier",
                height=330,
            )
        with c2:
            country = _distribution(filtered, "geo_country", value_map=COUNTRY_LABELS_EN)
            render_echart(
                donut_option(country, label="label", value="count", title="Country distribution"),
                key="chart_silent_country",
                height=330,
            )

        c1, c2 = st.columns(2)
        with c1:
            access = _distribution(filtered, "access_age_band", value_map=SILENT_ACCESS_AGE_LABELS, order=ACCESS_AGE_ORDER)
            render_echart(
                simple_bar_option(access, x="label", y="count", title="Access age band", color=PALETTE["cyan"]),
                key="chart_silent_access_age",
                height=330,
            )
        with c2:
            business = _distribution(filtered, "business_type")
            render_echart(
                simple_bar_option(business, x="label", y="count", title="Business type", color=PALETTE["green"]),
                key="chart_silent_business_type",
                height=330,
            )

    with tab_area:
        area = _area_rollup(filtered)
        if area.empty:
            empty_chart("No area data is available for the current filters.")
        else:
            render_echart(
                horizontal_bar_option(
                    area.head(20),
                    label="geo_reporting_name",
                    value="merchant_count",
                    title="Top activation areas",
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
                title="Top institutions",
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
                title="Institution concentration",
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
    st.sidebar.subheader("Silent merchant filters")
    filtered = df

    selected_country = mapped_multiselect_filter(
        "Country", filtered, "geo_country", key="silent_country", value_map=COUNTRY_LABELS_EN
    )
    if selected_country:
        filtered = filtered[filtered["geo_country"].astype(str).isin(selected_country)]

    filtered = _apply_geo_filters(filtered)

    selected_tier = mapped_multiselect_filter(
        "Silence tier", filtered, "silence_tier", key="silent_tier", value_map=SILENT_TIER_LABELS
    )
    if selected_tier:
        filtered = filtered[filtered["silence_tier"].astype(str).isin(selected_tier)]

    selected_age = mapped_multiselect_filter(
        "Access age band", filtered, "access_age_band", key="silent_age", value_map=SILENT_ACCESS_AGE_LABELS
    )
    if selected_age:
        filtered = filtered[filtered["access_age_band"].astype(str).isin(selected_age)]

    for label, column, key in (
        ("Business type", "business_type", "silent_business_type"),
        ("Institution group", "institution_group", "silent_institution_group"),
        ("Institution", "institution_name", "silent_institution"),
        ("MCC code", "mcc_code", "silent_mcc_code"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]

    address_scope = st.sidebar.selectbox("Address availability", list(ADDRESS_SCOPE_LABELS), key="silent_address_scope")
    filtered = _filter_address_scope(filtered, ADDRESS_SCOPE_LABELS[address_scope])

    bounds = _access_date_bounds(filtered)
    if bounds:
        value = st.sidebar.date_input(
            "Access date range",
            value=(bounds.start, bounds.end),
            min_value=bounds.start,
            max_value=bounds.end,
            key="silent_access_date_range",
        )
        if isinstance(value, tuple) and len(value) == 2:
            filtered = _filter_access_date_range(filtered, value[0], value[1])

    query = st.sidebar.text_input("Merchant / institution / area / ID keyword", key="silent_query")
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


def _apply_geo_filters(df: pd.DataFrame) -> pd.DataFrame:
    scope = country_scope(df)
    if scope == "NZ":
        return _apply_nz_geo_filters(df)
    if scope == "MIXED":
        selected_city = multiselect_filter("City", df, "geo_city", key="silent_geo_city")
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
        selected_city = multiselect_filter("City", filtered, "geo_city", key="silent_geo_city")
        if selected_city:
            filtered = filtered[filtered["geo_city"].astype(str).isin(selected_city)]

    area_key = "silent_nz_geo_area"
    if not selected_city:
        disabled_multiselect_filter(
            "NZ Geo Area",
            key=area_key,
            help_text="Select a City first, then choose a reviewed NZ Geo Area.",
        )
    elif not options(filtered, "nz_geo_area"):
        disabled_multiselect_filter(
            "NZ Geo Area",
            key=area_key,
            help_text="The selected City has no reviewed NZ Geo Area values.",
        )
    else:
        selected_area = multiselect_filter("NZ Geo Area", filtered, "nz_geo_area", key=area_key)
        if selected_area:
            filtered = filtered[filtered["nz_geo_area"].astype(str).isin(selected_area)]

    for label, column, key in (
        ("NZ Business Cluster", "nz_business_cluster", "silent_nz_cluster"),
        ("Suburb", "geo_suburb", "silent_geo_suburb"),
    ):
        selected = multiselect_filter(label, filtered, column, key=key)
        if selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]
    return filtered


def _apply_standard_geo_filters(df: pd.DataFrame, *, skip_columns: set[str] | None = None) -> pd.DataFrame:
    filtered = df
    skip_columns = skip_columns or set()
    for spec in _geo_filter_specs(country_scope(filtered)):
        if spec.column in skip_columns:
            continue
        selected = multiselect_filter(spec.label, filtered, spec.column, key=f"silent_{spec.key_suffix}")
        if selected:
            filtered = filtered[filtered[spec.column].astype(str).isin(selected)]
    return filtered


def _geo_filter_specs(scope: str) -> list[GeoFilterSpec]:
    if scope == "NZ":
        return [
            GeoFilterSpec("City", "geo_city", "geo_city"),
            GeoFilterSpec("NZ Geo Area", "nz_geo_area", "nz_geo_area"),
            GeoFilterSpec("NZ Business Cluster", "nz_business_cluster", "nz_cluster"),
            GeoFilterSpec("Suburb", "geo_suburb", "geo_suburb"),
        ]
    if scope == "AU":
        return [
            GeoFilterSpec("State", "geo_state", "geo_state"),
            GeoFilterSpec("City", "geo_city", "geo_city"),
            GeoFilterSpec("Suburb", "geo_suburb", "geo_suburb"),
            GeoFilterSpec("Postcode", "geo_postcode", "geo_postcode"),
        ]
    return [GeoFilterSpec("City", "geo_city", "geo_city")]


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
        out["label"] = out["value"].map(lambda value: value_map.get(value, value or "Unclassified"))
    else:
        out["label"] = out["value"].replace({"UNKNOWN": "Unclassified", "": "Unclassified"})
    return out[["label", "count"]]


def _area_rollup(df: pd.DataFrame) -> pd.DataFrame:
    if "geo_reporting_name" not in df.columns:
        return pd.DataFrame()
    working = df.copy()
    working["geo_reporting_name"] = working["geo_reporting_name"].fillna("").astype(str).str.strip()
    working.loc[working["geo_reporting_name"] == "", "geo_reporting_name"] = "Unmatched"
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
    working.loc[working["institution_name"] == "", "institution_name"] = "Unknown"
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
        "nz_geo_area": "NZ Geo Area",
        "nz_cluster": "NZ Business Cluster",
        "au_service_area": "AU Service Area",
        "au_city": "AU City",
        "au_state": "AU State",
        "au_suburb": "AU Suburb",
        "city": "City",
        "suburb": "Suburb",
        "postcode": "Postcode",
        "country": "Country",
        "unmatched": "Unmatched",
    }
    return mapping.get(str(value or ""), str(value or ""))


def _display_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "geo_country" in out.columns:
        out["geo_country"] = out["geo_country"].map(lambda value: COUNTRY_LABELS_EN.get(str(value), value))
    if "silence_tier" in out.columns:
        out["silence_tier"] = out["silence_tier"].map(lambda value: SILENT_TIER_LABELS.get(str(value), value))
    if "access_age_band" in out.columns:
        out["access_age_band"] = out["access_age_band"].map(lambda value: SILENT_ACCESS_AGE_LABELS.get(str(value), value))
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
            f"Current detail rows are a sample ({detail_count:,} of {aggregate_count:,} aggregate merchants). "
            "Charts, filters, and exports reflect the loaded detail rows."
        )


def _format_rate_value(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0]
    return format_pct(float(numeric))


_COLUMN_LABELS = {
    "merchant_id": "Merchant ID",
    "merchant_display_name": "Merchant Name",
    "institution_group": "Institution Group",
    "institution_name": "Institution",
    "geo_country": "Country",
    "geo_state": "State",
    "geo_city": "City",
    "geo_suburb": "Suburb",
    "geo_postcode": "Postcode",
    "geo_reporting_level": "Geo Level Code",
    "geo_reporting_level_label": "Geo Level",
    "geo_reporting_name": "Geo Reporting Name",
    "nz_geo_area": "NZ Geo Area",
    "silence_tier": "Silence Tier",
    "access_age_band": "Access Age Band",
    "merchant_access_time": "Access Time",
    "business_type": "Business Type",
    "mcc_code": "MCC Code",
    "txn_count_360d": "Txn Count 360d",
    "txn_amount_360d": "Txn Amount 360d",
    "address": "Address",
    "merchant_count": "Merchant Count",
    "new_unactivated_180d": "New Unactivated 180d",
    "initial_silent": "Initial Silent",
    "deep_silent": "Deep Silent",
    "address_count": "Address Count",
    "address_coverage": "Address Coverage",
}
