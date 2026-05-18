from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from streamlit_echarts import st_echarts


PALETTE = {
    "blue": "#5B9DFF",
    "cyan": "#35C2D8",
    "green": "#56C596",
    "yellow": "#F7C948",
    "orange": "#FF9F43",
    "red": "#FF5A5F",
    "purple": "#9B7EDE",
    "gray": "#8B95A7",
}

SEVERITY_COLORS = {
    "severe": "#FF5A5F",
    "high": "#FF9F43",
    "medium": "#F7C948",
    "stable": "#56C596",
}


def render_echart(options: dict[str, Any], *, key: str, height: int = 360) -> None:
    st_echarts(options=options, height=f"{height}px", renderer="canvas", key=key)


def combo_line_bar_option(
    df: pd.DataFrame,
    *,
    x: str,
    bar_y: str,
    line_y: str,
    title: str,
    bar_name: str,
    line_name: str,
) -> dict[str, Any]:
    source = [
        {
            x: _json_value(row.get(x)),
            bar_y: _json_value(row.get(bar_y)),
            line_y: round(float(row.get(line_y) or 0) * 100, 2),
        }
        for row in df.to_dict("records")
    ]
    return _base_option(title) | {
        "dataset": {"source": source},
        "legend": {"top": 8, "right": 12, "textStyle": {"color": "#C9D1D9"}},
        "xAxis": {"type": "category", "axisLabel": {"color": "#AAB2C0", "rotate": 35}},
        "yAxis": [
            {"type": "value", "name": bar_name, "axisLabel": {"color": "#AAB2C0"}},
            {
                "type": "value",
                "name": line_name,
                "axisLabel": {"color": "#AAB2C0", "formatter": "{value}%"},
                "splitLine": {"show": False},
            },
        ],
        "series": [
            {
                "name": bar_name,
                "type": "bar",
                "encode": {"x": x, "y": bar_y},
                "itemStyle": {"color": PALETTE["blue"], "borderRadius": [4, 4, 0, 0]},
                "barMaxWidth": 24,
            },
            {
                "name": line_name,
                "type": "line",
                "yAxisIndex": 1,
                "encode": {"x": x, "y": line_y},
                "smooth": True,
                "symbolSize": 7,
                "lineStyle": {"width": 3, "color": PALETTE["orange"]},
                "itemStyle": {"color": PALETTE["orange"]},
            },
        ],
    }


def stacked_bar_option(
    df: pd.DataFrame,
    *,
    category: str,
    value_columns: list[str],
    title: str,
) -> dict[str, Any]:
    rows = df.to_dict("records")
    return _base_option(title) | {
        "dataset": {"source": [{key: _json_value(value) for key, value in row.items()} for row in rows]},
        "legend": {"top": 8, "right": 12, "textStyle": {"color": "#C9D1D9"}},
        "xAxis": {"type": "category", "axisLabel": {"color": "#AAB2C0", "rotate": 35}},
        "yAxis": {"type": "value", "axisLabel": {"color": "#AAB2C0"}},
        "series": [
            {
                "name": col,
                "type": "bar",
                "stack": "total",
                "encode": {"x": category, "y": col},
                "barMaxWidth": 26,
            }
            for col in value_columns
        ],
    }


def horizontal_bar_option(
    df: pd.DataFrame,
    *,
    label: str,
    value: str,
    title: str,
    color: str = PALETTE["blue"],
) -> dict[str, Any]:
    rows = list(reversed(df.to_dict("records")))
    return _base_option(title) | {
        "grid": {"left": 140, "right": 28, "top": 60, "bottom": 28},
        "xAxis": {"type": "value", "axisLabel": {"color": "#AAB2C0"}},
        "yAxis": {
            "type": "category",
            "data": [_json_value(row.get(label)) for row in rows],
            "axisLabel": {"color": "#C9D1D9", "width": 120, "overflow": "truncate"},
        },
        "series": [
            {
                "type": "bar",
                "data": [_json_value(row.get(value)) for row in rows],
                "itemStyle": {"color": color, "borderRadius": [0, 5, 5, 0]},
                "label": {"show": True, "position": "right", "color": "#C9D1D9"},
                "barMaxWidth": 18,
            }
        ],
    }


def simple_bar_option(df: pd.DataFrame, *, x: str, y: str, title: str, color: str = PALETTE["blue"]) -> dict[str, Any]:
    return _base_option(title) | {
        "xAxis": {"type": "category", "data": df[x].astype(str).tolist(), "axisLabel": {"color": "#AAB2C0"}},
        "yAxis": {"type": "value", "axisLabel": {"color": "#AAB2C0"}},
        "series": [
            {
                "type": "bar",
                "data": [_json_value(value) for value in df[y].tolist()],
                "itemStyle": {"color": color, "borderRadius": [5, 5, 0, 0]},
                "barMaxWidth": 30,
            }
        ],
    }


def donut_option(
    df: pd.DataFrame,
    *,
    label: str,
    value: str,
    title: str,
    color_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = [
        {
            "name": str(row.get(label) or "UNKNOWN"),
            "value": _json_value(row.get(value)),
            **(
                {"itemStyle": {"color": color_map[str(row.get(label))]}}
                if color_map and str(row.get(label)) in color_map
                else {}
            ),
        }
        for row in df.to_dict("records")
    ]
    return _base_option(title) | {
        "legend": {"orient": "vertical", "right": 12, "top": 44, "textStyle": {"color": "#C9D1D9"}},
        "series": [
            {
                "type": "pie",
                "radius": ["48%", "72%"],
                "center": ["40%", "56%"],
                "avoidLabelOverlap": True,
                "label": {"show": False},
                "emphasis": {"label": {"show": True, "formatter": "{b}\n{d}%", "color": "#F2F5F8"}},
                "data": data,
            }
        ],
    }


def treemap_option(df: pd.DataFrame, *, label: str, value: str, title: str) -> dict[str, Any]:
    data = [
        {"name": str(row.get(label) or "UNKNOWN"), "value": _json_value(row.get(value))}
        for row in df.to_dict("records")
    ]
    return _base_option(title) | {
        "series": [
            {
                "type": "treemap",
                "roam": False,
                "breadcrumb": {"show": False},
                "label": {"show": True, "formatter": "{b}", "color": "#F2F5F8"},
                "upperLabel": {"show": False},
                "itemStyle": {"borderColor": "#10151F", "borderWidth": 2, "gapWidth": 2},
                "data": data,
            }
        ]
    }


def empty_chart(message: str = "No data for this chart.") -> None:
    st.info(message)


def _base_option(title: str) -> dict[str, Any]:
    return {
        "backgroundColor": "transparent",
        "color": [
            PALETTE["blue"],
            PALETTE["cyan"],
            PALETTE["green"],
            PALETTE["yellow"],
            PALETTE["orange"],
            PALETTE["red"],
            PALETTE["purple"],
        ],
        "title": {"text": title, "left": 4, "top": 2, "textStyle": {"color": "#F2F5F8", "fontSize": 15}},
        "tooltip": {"trigger": "axis", "confine": True, "backgroundColor": "#111827", "borderColor": "#303846"},
        "grid": {"left": 72, "right": 42, "top": 62, "bottom": 54},
    }


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return ""
    if hasattr(value, "item"):
        return value.item()
    return value
