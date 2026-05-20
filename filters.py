from __future__ import annotations

from typing import Iterable

import pandas as pd
import streamlit as st

from data_io import duckdb_filter_frame
from ui_labels import label_value


KA_SCOPE_ALL = "全部商户"
KA_SCOPE_ONLY = "只看KA"
KA_SCOPE_EXCLUDE = "剔除KA"


def options(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str)
    return sorted(value for value in values.unique() if value and value.lower() != "nan")


def multiselect_filter(
    label: str,
    df: pd.DataFrame,
    column: str,
    *,
    key: str,
    disabled: bool = False,
    help_text: str | None = None,
) -> list[str]:
    values = options(df, column)
    if disabled:
        return disabled_multiselect_filter(label, key=key, help_text=help_text)
    if not values:
        return []
    _prune_multiselect_state(key, values)
    return st.sidebar.multiselect(label, values, key=key, help=help_text)


def mapped_multiselect_filter(
    label: str,
    df: pd.DataFrame,
    column: str,
    *,
    key: str,
    value_map: dict[str, str],
    help_text: str | None = None,
) -> list[str]:
    values = options(df, column)
    if not values:
        return []
    labels = [label_value(value, value_map) for value in values]
    _prune_multiselect_state(key, labels)
    selected_labels = st.sidebar.multiselect(label, labels, key=key, help=help_text)
    selected = set(selected_labels)
    return [value for value in values if label_value(value, value_map) in selected]


def disabled_multiselect_filter(label: str, *, key: str, help_text: str | None = None) -> list[str]:
    if key in st.session_state:
        del st.session_state[key]
    try:
        st.sidebar.multiselect(label, [], key=key, disabled=True, help=help_text)
    except TypeError:
        st.sidebar.caption(f"{label}: {help_text or 'Select the required parent filter first.'}")
    return []


def apply_in_filter(df: pd.DataFrame, column: str, selected: Iterable[str]) -> pd.DataFrame:
    selected = [str(value) for value in selected if str(value)]
    if not selected or column not in df.columns:
        return df
    placeholders = ", ".join("?" for _ in selected)
    try:
        return duckdb_filter_frame(
            df,
            where_sql=f"cast({_quote_identifier(column)} as varchar) in ({placeholders})",
            parameters=tuple(selected),
        )
    except Exception:
        return df[df[column].astype(str).isin(selected)]


def apply_text_filter(df: pd.DataFrame, columns: list[str], query: str) -> pd.DataFrame:
    query = str(query or "").strip().casefold()
    if not query:
        return df
    existing = [column for column in columns if column in df.columns]
    if not existing:
        return df
    where_sql = " or ".join(
        f"contains(lower(coalesce(cast({_quote_identifier(column)} as varchar), '')), ?)"
        for column in existing
    )
    try:
        return duckdb_filter_frame(df, where_sql=where_sql, parameters=tuple(query for _ in existing))
    except Exception:
        mask = pd.Series(False, index=df.index)
        for column in existing:
            mask = mask | df[column].fillna("").astype(str).str.casefold().str.contains(query, regex=False)
        return df[mask]


def ka_scope_filter(df: pd.DataFrame, *, key: str) -> pd.DataFrame:
    if "merchant_segment" not in df.columns and "is_ka" not in df.columns:
        return df
    scope = st.sidebar.selectbox(
        "KA/SMB范围",
        (KA_SCOPE_ALL, KA_SCOPE_ONLY, KA_SCOPE_EXCLUDE),
        key=key,
        help="KA 来自共享 KA MID 维表；剔除 KA 后即为 SMB/非 KA 商户。",
    )
    return apply_ka_scope(df, scope)


def apply_ka_scope(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == KA_SCOPE_ALL:
        return df
    if "merchant_segment" in df.columns:
        segment = df["merchant_segment"].fillna("").astype(str).str.upper()
        is_ka = segment.eq("KA")
    elif "is_ka" in df.columns:
        is_ka = pd.to_numeric(df["is_ka"], errors="coerce").fillna(0).astype(int).eq(1)
    else:
        return df
    if scope == KA_SCOPE_ONLY:
        return df[is_ka]
    if scope == KA_SCOPE_EXCLUDE:
        return df[~is_ka]
    return df


def number(value: object) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _prune_multiselect_state(key: str, valid_values: list[str]) -> None:
    if key not in st.session_state:
        return
    current = st.session_state.get(key)
    if not isinstance(current, list):
        return
    valid = set(valid_values)
    pruned = [value for value in current if value in valid]
    if pruned != current:
        st.session_state[key] = pruned


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'
