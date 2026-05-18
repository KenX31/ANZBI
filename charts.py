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


def combo_bar_count_line_option(
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
            line_y: _json_value(row.get(line_y)),
        }
        for row in df.to_dict("records")
    ]
    return _base_option(title) | {
        "dataset": {"source": source},
        "legend": {"top": 8, "right": 12, "textStyle": {"color": TEXT_MUTED}},
        "xAxis": _category_axis(),
        "yAxis": [
            _value_axis(name=bar_name),
            {
                "type": "value",
                "name": line_name,
                "axisLabel": {"color": TEXT_MUTED},
                "splitLine": {"show": False},
                "axisLine": {"lineStyle": {"color": BORDER}},
            },
        ],
        "series": [
            {
                "name": bar_name,
                "type": "bar",
                "encode": {"x": x, "y": bar_y},
                "itemStyle": {"color": PALETTE["cyan"], "borderRadius": [5, 5, 0, 0]},
                "barMaxWidth": 30,
            },
            {
                "name": line_name,
                "type": "line",
                "yAxisIndex": 1,
                "encode": {"x": x, "y": line_y},
                "smooth": True,
                "symbolSize": 8,
                "lineStyle": {"width": 4, "color": PALETTE["green"]},
                "itemStyle": {"color": PALETTE["green"], "borderColor": PALETTE["forest"], "borderWidth": 2},
                "label": {"show": True, "position": "top", "color": TEXT_MUTED},
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
        "tooltip": _item_tooltip(),
        "legend": {"orient": "vertical", "right": 12, "top": 44, "textStyle": {"color": TEXT_MUTED}},
        "series": [
            {
                "type": "pie",
                "radius": ["42%", "66%"],
                "center": ["36%", "56%"],
                "avoidLabelOverlap": True,
                "label": {
                    "show": True,
                    "position": "outside",
                    "formatter": "{b}\n{d}%",
                    "color": TEXT_DARK,
                    "fontWeight": 500,
                },
                "labelLine": {"show": True, "length": 12, "length2": 8, "lineStyle": {"color": BORDER}},
                "itemStyle": {"borderColor": PALETTE["white"], "borderWidth": 2},
                "emphasis": {"label": {"show": True, "formatter": "{b}\n{d}%", "color": TEXT_DARK}},
                "data": data,
            }
        ],
    }


def treemap_option(
    df: pd.DataFrame,
    *,
    label: str,
    value: str,
    title: str,
    color_by: str | None = None,
    color_name: str = "",
    high_is_good: bool = True,
) -> dict[str, Any]:
    total = pd.to_numeric(df[value], errors="coerce").fillna(0).sum() if value in df.columns else 0
    data = [
        _treemap_item(
            row,
            label=label,
            value=value,
            total=float(total or 0),
            color_by=color_by,
            color_name=color_name,
            high_is_good=high_is_good,
        )
        for row in df.to_dict("records")
    ]
    return _base_option(title) | {
        "tooltip": _item_tooltip(),
        "series": [
            {
                "type": "treemap",
                "roam": False,
                "breadcrumb": {"show": False},
                "label": {"show": True, "color": PALETTE["white"], "fontWeight": 600, "fontSize": 12},
                "upperLabel": {"show": False},
                "itemStyle": {"borderColor": PALETTE["white"], "borderWidth": 2, "gapWidth": 2},
                "data": data,
            }
        ]
    }


def empty_chart(message: str = "当前筛选下没有可展示的数据。") -> None:
    st.info(message)


def _treemap_item(
    row: dict[str, Any],
    *,
    label: str,
    value: str,
    total: float,
    color_by: str | None,
    color_name: str,
    high_is_good: bool,
) -> dict[str, Any]:
    name = str(row.get(label) or "UNKNOWN")
    count = float(row.get(value) or 0)
    share = count / total if total else 0
    lines = [name, f"占比 {share:.1%}"]
    item: dict[str, Any] = {
        "name": name,
        "value": _json_value(row.get(value)),
        "label": {"formatter": "\n".join(lines)},
    }
    if color_by:
        rate = _bounded_rate(row.get(color_by))
        if color_name:
            lines.append(f"{color_name} {rate:.1%}")
            item["label"] = {"formatter": "\n".join(lines)}
        item["itemStyle"] = {"color": _rate_color(rate, high_is_good=high_is_good)}
    return item


def _bounded_rate(value: Any) -> float:
    try:
        rate = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, rate))


def _rate_color(rate: float, *, high_is_good: bool) -> str:
    if high_is_good:
        return _blend_color(PALETTE["cool_gray"], PALETTE["green"], rate)
    return _blend_color(PALETTE["green"], PALETTE["forest"], rate)


def _blend_color(start: str, end: str, ratio: float) -> str:
    start_rgb = _hex_to_rgb(start)
    end_rgb = _hex_to_rgb(end)
    mixed = tuple(round(s + (e - s) * ratio) for s, e in zip(start_rgb, end_rgb))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    cleaned = value.lstrip("#")
    return tuple(int(cleaned[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _item_tooltip() -> dict[str, Any]:
    return {
        "trigger": "item",
        "confine": True,
        "backgroundColor": PALETTE["forest"],
        "borderColor": PALETTE["teal_gray"],
        "textStyle": {"color": PALETTE["white"]},
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
