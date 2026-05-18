from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from streamlit_echarts import st_echarts


PALETTE = {
    "forest": "#001e2b",
    "green": "#00ed64",
    "dark_green": "#00684a",
    "blue": "#006cfa",
    "hover_blue": "#3860be",
    "cyan": "#1eaedb",
    "deep_teal": "#1c2d38",
    "teal_gray": "#3d4f58",
    "cool_gray": "#5c6c75",
    "silver": "#b8c4c2",
    "input": "#e8edeb",
    "white": "#ffffff",
    "red": "#006cfa",
    "orange": "#00ed64",
    "yellow": "#1eaedb",
    "purple": "#3d4f58",
    "gray": "#5c6c75",
}

SEVERITY_COLORS = {
    "severe": PALETTE["forest"],
    "high": PALETTE["blue"],
    "medium": PALETTE["cyan"],
    "stable": PALETTE["green"],
}

TEXT_DARK = PALETTE["forest"]
TEXT_MUTED = PALETTE["cool_gray"]
BORDER = PALETTE["silver"]
GRID_LINE = "#d8e1df"


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
        "legend": {"top": 8, "right": 12, "textStyle": {"color": TEXT_MUTED}},
        "xAxis": _category_axis(rotate=35),
        "yAxis": [
            _value_axis(name=bar_name),
            {
                "type": "value",
                "name": line_name,
                "axisLabel": {"color": TEXT_MUTED, "formatter": "{value}%"},
                "splitLine": {"show": False},
                "axisLine": {"lineStyle": {"color": BORDER}},
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
                "lineStyle": {"width": 3, "color": PALETTE["green"]},
                "itemStyle": {"color": PALETTE["green"], "borderColor": PALETTE["white"], "borderWidth": 2},
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
        "legend": {"top": 8, "right": 12, "textStyle": {"color": TEXT_MUTED}},
        "xAxis": _category_axis(rotate=35),
        "yAxis": _value_axis(),
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
        "xAxis": _value_axis(),
        "yAxis": {
            "type": "category",
            "data": [_json_value(row.get(label)) for row in rows],
            "axisLabel": {"color": TEXT_DARK, "width": 120, "overflow": "truncate", "fontWeight": 500},
            "axisLine": {"lineStyle": {"color": BORDER}},
            "axisTick": {"show": False},
        },
        "series": [
            {
                "type": "bar",
                "data": [_json_value(row.get(value)) for row in rows],
                "itemStyle": {"color": color, "borderRadius": [0, 5, 5, 0]},
                "label": {"show": True, "position": "right", "color": TEXT_MUTED},
                "barMaxWidth": 18,
            }
        ],
    }


def simple_bar_option(df: pd.DataFrame, *, x: str, y: str, title: str, color: str = PALETTE["blue"]) -> dict[str, Any]:
    return _base_option(title) | {
        "xAxis": _category_axis(data=df[x].astype(str).tolist()),
        "yAxis": _value_axis(),
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
        "legend": {"orient": "vertical", "right": 12, "top": 44, "textStyle": {"color": TEXT_MUTED}},
        "series": [
            {
                "type": "pie",
                "radius": ["48%", "72%"],
                "center": ["40%", "56%"],
                "avoidLabelOverlap": True,
                "label": {"show": False},
                "itemStyle": {"borderColor": PALETTE["white"], "borderWidth": 2},
                "emphasis": {"label": {"show": True, "formatter": "{b}\n{d}%", "color": TEXT_DARK}},
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
                "label": {"show": True, "formatter": "{b}", "color": PALETTE["white"], "fontWeight": 500},
                "upperLabel": {"show": False},
                "itemStyle": {"borderColor": PALETTE["white"], "borderWidth": 2, "gapWidth": 2},
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
            PALETTE["green"],
            PALETTE["blue"],
            PALETTE["cyan"],
            PALETTE["dark_green"],
            PALETTE["deep_teal"],
            PALETTE["hover_blue"],
            PALETTE["teal_gray"],
        ],
        "title": {"text": title, "left": 4, "top": 2, "textStyle": {"color": TEXT_DARK, "fontSize": 15, "fontWeight": 600}},
        "tooltip": {
            "trigger": "axis",
            "confine": True,
            "backgroundColor": PALETTE["forest"],
            "borderColor": PALETTE["teal_gray"],
            "textStyle": {"color": PALETTE["white"]},
        },
        "grid": {"left": 72, "right": 42, "top": 62, "bottom": 54},
    }


def _category_axis(*, data: list[str] | None = None, rotate: int = 0) -> dict[str, Any]:
    axis = {
        "type": "category",
        "axisLabel": {"color": TEXT_MUTED, "rotate": rotate},
        "axisLine": {"lineStyle": {"color": BORDER}},
        "axisTick": {"show": False},
    }
    if data is not None:
        axis["data"] = data
    return axis


def _value_axis(*, name: str | None = None) -> dict[str, Any]:
    axis: dict[str, Any] = {
        "type": "value",
        "axisLabel": {"color": TEXT_MUTED},
        "axisLine": {"lineStyle": {"color": BORDER}},
        "splitLine": {"lineStyle": {"color": GRID_LINE}},
    }
    if name:
        axis["name"] = name
        axis["nameTextStyle"] = {"color": TEXT_MUTED}
    return axis


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return ""
    if hasattr(value, "item"):
        return value.item()
    return value
