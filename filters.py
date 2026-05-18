from __future__ import annotations

from typing import Iterable

import pandas as pd
import streamlit as st


def options(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str)
    return sorted(value for value in values.unique() if value and value.lower() != "nan")


def multiselect_filter(label: str, df: pd.DataFrame, column: str, *, key: str) -> list[str]:
    values = options(df, column)
    if not values:
        return []
    return st.sidebar.multiselect(label, values, key=key)


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

