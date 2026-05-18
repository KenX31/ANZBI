from __future__ import annotations

import pandas as pd


def sum_number(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns or df.empty:
        return 0.0
    return pd.to_numeric(df[column], errors="coerce").fillna(0).sum()


def count_flag(df: pd.DataFrame, column: str, value: object = 1) -> int:
    if column not in df.columns or df.empty:
        return 0
    return int((df[column].fillna("").astype(str) == str(value)).sum())


def rate(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def format_int(value: float) -> str:
    return f"{int(round(value)):,}"


def format_money(value: float) -> str:
    return f"{value:,.0f}"


def format_pct(value: float) -> str:
    return f"{value:.1%}"

