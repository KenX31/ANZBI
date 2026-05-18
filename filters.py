from __future__ import annotations

from typing import Iterable

import pandas as pd
import streamlit as st

from ui_labels import label_value


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
    return df[df[column].astype(str).isin(selected)]


def apply_text_filter(df: pd.DataFrame, columns: list[str], query: str) -> pd.DataFrame:
    query = str(query or "").strip().casefold()
    if not query:
        return df
    mask = pd.Series(False, index=df.index)
    for column in columns:
        if column in df.columns:
            mask = mask | df[column].fillna("").astype(str).str.casefold().str.contains(query, regex=False)
    return df[mask]


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
