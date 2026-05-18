from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


DEFAULT_COUNTRY_COLUMNS = ("analysis_country", "scope_country", "country_group", "merchant_country_code")
UNKNOWN_VALUES = {"", "nan", "none", "null", "unknown", "未分类", "未识别城市/地址缺失"}

LEVEL_LABELS = {
    "nz_geo_area": "NZ geo area",
    "nz_cluster": "NZ cluster",
    "au_service_area": "AU service area",
    "au_city": "AU city",
    "au_state": "AU state",
    "au_suburb": "AU suburb",
    "city": "City",
    "suburb": "Suburb",
    "postcode": "Postcode",
    "country": "Country",
    "unmatched": "Unmatched",
}


@dataclass(frozen=True)
class GeoFilterSpec:
    label: str
    column: str
    key_suffix: str


def with_reporting_geography(
    df: pd.DataFrame,
    *,
    country_columns: str | Iterable[str] | None = None,
) -> pd.DataFrame:
    """Add country-aware geography columns without changing source fields.

    NZ keeps its geo_area / business_cluster layer. AU does not pretend to have
    the same layer; its reporting fallback is service area when available, then
    city/state/suburb/postcode.
    """

    out = df.copy()
    countries = _as_columns(country_columns) or list(DEFAULT_COUNTRY_COLUMNS)

    out["geo_country"] = _first_text(out, _staging_or_fallback(out, "staging_country", countries)).map(normalize_country)
    out["geo_state"] = _first_text(
        out, _staging_or_fallback(out, "staging_state", ["geo_state", "business_state", "state", "State", "province"])
    )
    out["geo_city"] = _first_text(
        out, _staging_or_fallback(out, "staging_city", ["geo_city", "business_city", "city", "City"])
    )
    out["geo_suburb"] = _first_text(
        out, _staging_or_fallback(out, "staging_suburb", ["geo_suburb", "business_suburb", "suburb", "Suburb"])
    )
    out["geo_postcode"] = _first_text(
        out, _staging_or_fallback(out, "staging_postcode", ["geo_postcode", "postcode", "Postcode"])
    )

    nz_mask = out["geo_country"].eq("NZ")
    au_mask = out["geo_country"].eq("AU")

    out["nz_geo_area"] = ""
    nz_geo_area_sources = ["staging_geo_area"] if "staging_geo_area" in out.columns else ["nz_geo_area", "geo_area"]
    out.loc[nz_mask, "nz_geo_area"] = _first_text(out.loc[nz_mask], nz_geo_area_sources)
    out["nz_business_cluster"] = ""
    nz_cluster_sources = (
        ["staging_business_cluster"]
        if "staging_business_cluster" in out.columns
        else ["nz_business_cluster", "business_cluster"]
    )
    out.loc[nz_mask, "nz_business_cluster"] = _first_text(
        out.loc[nz_mask], nz_cluster_sources
    )

    out["au_service_area"] = ""
    out.loc[au_mask, "au_service_area"] = _first_text(out.loc[au_mask], ["au_service_area", "service_area"])

    out["geo_reporting_level"] = "unmatched"
    out["geo_reporting_name"] = ""

    _assign_reporting(out, nz_mask & _valid(out["nz_geo_area"]), "nz_geo_area", out["nz_geo_area"])
    _assign_reporting(
        out,
        nz_mask & _valid(out["nz_business_cluster"]) & _missing_reporting(out),
        "nz_cluster",
        out["nz_business_cluster"],
    )
    _assign_reporting(out, au_mask & _valid(out["au_service_area"]), "au_service_area", out["au_service_area"])
    _assign_reporting(out, au_mask & _valid(out["geo_city"]) & _missing_reporting(out), "au_city", out["geo_city"])
    _assign_reporting(out, au_mask & _valid(out["geo_state"]) & _missing_reporting(out), "au_state", out["geo_state"])
    _assign_reporting(out, au_mask & _valid(out["geo_suburb"]) & _missing_reporting(out), "au_suburb", out["geo_suburb"])
    _assign_reporting(out, _valid(out["geo_city"]) & _missing_reporting(out), "city", out["geo_city"])
    _assign_reporting(out, _valid(out["geo_suburb"]) & _missing_reporting(out), "suburb", out["geo_suburb"])
    _assign_reporting(out, _valid(out["geo_postcode"]) & _missing_reporting(out), "postcode", out["geo_postcode"])
    _assign_reporting(out, _valid(out["geo_country"]) & _missing_reporting(out), "country", out["geo_country"])

    out["geo_reporting_level_label"] = out["geo_reporting_level"].map(LEVEL_LABELS).fillna(
        out["geo_reporting_level"]
    )
    return out


def normalize_country(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"NZ", "554", "NEW ZEALAND"}:
        return "NZ"
    if text in {"AU", "036", "36", "AUS", "AUSTRALIA"}:
        return "AU"
    return text


def country_scope(df: pd.DataFrame, country_column: str = "geo_country") -> str:
    if country_column not in df.columns:
        return "MIXED"
    values = {
        normalize_country(value)
        for value in df[country_column].dropna().astype(str)
        if _is_valid_text(value)
    }
    if values == {"NZ"}:
        return "NZ"
    if values == {"AU"}:
        return "AU"
    if not values:
        return "UNKNOWN"
    return "MIXED"


def sidebar_geo_filter_specs(scope: str) -> list[GeoFilterSpec]:
    if scope == "NZ":
        return [
            GeoFilterSpec("City", "geo_city", "geo_city"),
            GeoFilterSpec("NZ geo area", "nz_geo_area", "nz_geo_area"),
            GeoFilterSpec("NZ cluster", "nz_business_cluster", "nz_cluster"),
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


def geo_reporting_bridge_contract() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "country": "NZ",
                "reporting_level": "nz_geo_area",
                "source_columns": "geo_area",
                "streamlit_filters": "City,NZ geo area,NZ cluster,Suburb",
                "notes": "Primary NZ operating geography.",
            },
            {
                "country": "NZ",
                "reporting_level": "nz_cluster",
                "source_columns": "business_cluster",
                "streamlit_filters": "City,NZ geo area,NZ cluster,Suburb",
                "notes": "NZ cluster fallback when geo_area is missing.",
            },
            {
                "country": "AU",
                "reporting_level": "au_service_area",
                "source_columns": "au_service_area,service_area",
                "streamlit_filters": "State,City,Suburb,Postcode",
                "notes": "Optional future AU operating area; not equivalent to NZ geo_area.",
            },
            {
                "country": "AU",
                "reporting_level": "au_city",
                "source_columns": "business_city,city",
                "streamlit_filters": "State,City,Suburb,Postcode",
                "notes": "Default AU reporting geography until AU service areas are reviewed.",
            },
            {
                "country": "ALL",
                "reporting_level": "city",
                "source_columns": "business_city,city",
                "streamlit_filters": "Country,City",
                "notes": "Shared cross-country geography for mixed AU/NZ views.",
            },
        ]
    )


def _assign_reporting(df: pd.DataFrame, mask: pd.Series, level: str, names: pd.Series) -> None:
    if len(df) == 0:
        return
    df.loc[mask, "geo_reporting_level"] = level
    df.loc[mask, "geo_reporting_name"] = names.loc[mask].fillna("").astype(str).str.strip()


def _missing_reporting(df: pd.DataFrame) -> pd.Series:
    return ~_valid(df["geo_reporting_name"])


def _valid(values: pd.Series) -> pd.Series:
    return values.fillna("").astype(str).map(_is_valid_text)


def _is_valid_text(value: object) -> bool:
    return str(value or "").strip().casefold() not in UNKNOWN_VALUES


def _first_text(df: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    result = pd.Series([""] * len(df), index=df.index, dtype=object)
    for column in columns:
        if column not in df.columns:
            continue
        values = df[column].fillna("").astype(str).str.strip()
        result = result.where(result.astype(str).str.strip() != "", values)
    return result.fillna("")


def _as_columns(columns: str | Iterable[str] | None) -> list[str]:
    if columns is None:
        return []
    if isinstance(columns, str):
        return [columns]
    return [str(column) for column in columns]


def _staging_or_fallback(df: pd.DataFrame, staging_column: str, fallback_columns: Iterable[str]) -> list[str]:
    if staging_column in df.columns:
        return [staging_column]
    return list(fallback_columns)
