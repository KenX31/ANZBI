from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


UNKNOWN_CITY_LABELS = {"", "UNKNOWN", "未分类", "未识别城市/地址缺失", "nan"}
CITY_ALIASES = {
    "NZ": {
        "Wellington Metro": ("wellington", "lower hutt", "upper hutt", "porirua"),
        "Auckland": ("auckland",),
        "Christchurch": ("christchurch",),
        "Queenstown": ("queenstown",),
        "Hamilton": ("hamilton",),
        "Rotorua": ("rotorua",),
        "Tauranga": ("tauranga",),
        "Dunedin": ("dunedin",),
    },
    "AU": {
        "Sydney": ("sydney",),
        "Melbourne": ("melbourne",),
        "Brisbane": ("brisbane",),
        "Gold Coast": ("gold coast", "southport", "surfers paradise"),
        "Perth": ("perth",),
        "Adelaide": ("adelaide",),
        "Canberra": ("canberra",),
        "Hobart": ("hobart",),
        "Darwin": ("darwin",),
        "Cairns": ("cairns",),
    },
}


@dataclass(frozen=True)
class GeoMatchResult:
    country: str
    state: str = ""
    city: str = ""
    suburb: str = ""
    geo_area: str = ""
    business_cluster: str = ""
    postcode: str = ""
    source: str = "unmatched"


class StreamlitGeoMatcher:
    def __init__(self, staging_dir: Path):
        self.staging_dir = staging_dir
        self.nz = _read_csv(staging_dir / "nz_geo_dimension.csv")
        self.au = _read_csv(staging_dir / "au_geo_dimension.csv")
        self.nz_rules = _read_csv(staging_dir / "nz_geo_area_rules.csv")
        self.au_rules = _read_csv(staging_dir / "au_geo_match_rules.csv")
        self.nz_by_postcode = _by_postcode(self.nz, "Postcode")
        self.au_by_postcode = _by_postcode(self.au, "Postcode")
        self.au_manual_rules = _manual_au_rules(self.au_rules)
        self.nz_aliases = _suburb_aliases(self.nz_rules, country="NZ")
        self.au_aliases = _suburb_aliases(self.au, country="AU")

    def match_row(self, row: dict[str, Any]) -> GeoMatchResult:
        country = _country(row)
        name = _text(
            row.get("merchant_short_name")
            or row.get("merchant_name")
            or row.get("merchant_company_name")
            or ""
        )
        address = _text(row.get("store_address") or row.get("address") or "")
        postcode = _normalize_postcode(row.get("postcode") or row.get("Postcode")) or _extract_postcode(address)
        city_from_name = _city_from_text(country, name)

        if country == "NZ":
            return self._match_nz(address=address, postcode=postcode, city_from_name=city_from_name)
        if country == "AU":
            return self._match_au(address=address, postcode=postcode, city_from_name=city_from_name)
        return GeoMatchResult(country=country or "UNKNOWN")

    def _match_nz(self, *, address: str, postcode: str, city_from_name: str) -> GeoMatchResult:
        if postcode and postcode in self.nz_by_postcode:
            row = _pick_best_row(self.nz_by_postcode[postcode], address)
            return GeoMatchResult(
                country="NZ",
                city=_text(row.get("City")),
                suburb=_text(row.get("Suburb")),
                geo_area=_text(row.get("geo_area")),
                business_cluster=_text(row.get("business_cluster")),
                postcode=postcode,
                source="nz_postcode_lookup",
            )

        if city_from_name:
            return GeoMatchResult(country="NZ", city=city_from_name, source="merchant_short_name_city")

        alias = _find_alias(address, self.nz_aliases)
        if alias is not None:
            return GeoMatchResult(
                country="NZ",
                city=_text(alias.get("City")),
                suburb=_text(alias.get("Suburb")),
                geo_area=_text(alias.get("geo_area")),
                business_cluster=_text(alias.get("business_cluster")),
                postcode=_text(alias.get("Postcode")),
                source="nz_suburb_alias",
            )

        city_from_address = _city_from_text("NZ", address)
        if city_from_address:
            return GeoMatchResult(country="NZ", city=city_from_address, source="nz_address_city_keyword")
        return GeoMatchResult(country="NZ")

    def _match_au(self, *, address: str, postcode: str, city_from_name: str) -> GeoMatchResult:
        if postcode and postcode in self.au_by_postcode:
            row = _pick_best_row(self.au_by_postcode[postcode], address)
            return GeoMatchResult(
                country="AU",
                state=_text(row.get("State")),
                city=_text(row.get("City")),
                suburb=_text(row.get("Suburb")),
                postcode=postcode,
                source="au_postcode_lookup",
            )

        if city_from_name:
            return GeoMatchResult(
                country="AU",
                city=city_from_name,
                source="merchant_short_name_city",
            )

        manual = _find_manual_au_rule(address, postcode, self.au_manual_rules)
        if manual is not None:
            return GeoMatchResult(
                country="AU",
                state=_text(manual.get("State")),
                city=_text(manual.get("City")),
                suburb=_text(manual.get("Suburb")),
                geo_area=_text(manual.get("area_hint")),
                business_cluster=_text(manual.get("business_cluster")),
                postcode=_text(manual.get("Postcode")) or postcode,
                source="au_manual_override",
            )

        alias = _find_alias(address, self.au_aliases)
        if alias is not None:
            return GeoMatchResult(
                country="AU",
                state=_text(alias.get("State")),
                city=_text(alias.get("City")),
                suburb=_text(alias.get("Suburb")),
                postcode=_text(alias.get("Postcode")),
                source="au_suburb_alias",
            )

        city_from_address = _city_from_text("AU", address)
        if city_from_address:
            return GeoMatchResult(country="AU", city=city_from_address, source="au_address_city_keyword")
        return GeoMatchResult(country="AU")


def append_staging_geo_columns(rows: pd.DataFrame, matcher: StreamlitGeoMatcher) -> pd.DataFrame:
    out = rows.copy()
    if out.empty:
        for column in (
            "staging_country",
            "staging_state",
            "staging_city",
            "staging_suburb",
            "staging_geo_area",
            "staging_business_cluster",
            "staging_postcode",
            "staging_geo_source",
        ):
            out[column] = []
        return out

    matched = [matcher.match_row(record) for record in out.to_dict("records")]
    staged = pd.DataFrame(
        [
            {
                "staging_country": item.country,
                "staging_state": item.state,
                "staging_city": item.city,
                "staging_suburb": item.suburb,
                "staging_geo_area": item.geo_area,
                "staging_business_cluster": item.business_cluster,
                "staging_postcode": item.postcode,
                "staging_geo_source": item.source,
            }
            for item in matched
        ],
        index=out.index,
    )
    for column in staged.columns:
        out[column] = staged[column]
    return out


def compare_geo_coverage(rows: pd.DataFrame, matcher: StreamlitGeoMatcher) -> dict[str, Any]:
    current = {
        "city": _coverage(rows, "business_city"),
        "suburb": _coverage(rows, "business_suburb"),
        "geo_area": _coverage(rows, "geo_area"),
        "cluster": _coverage(rows, "business_cluster"),
    }
    matched = [matcher.match_row(record) for record in rows.to_dict("records")]
    staged = pd.DataFrame(
        [
            {
                "staging_city": item.city,
                "staging_suburb": item.suburb,
                "staging_geo_area": item.geo_area,
                "staging_business_cluster": item.business_cluster,
                "staging_source": item.source,
            }
            for item in matched
        ]
    )
    staging = {
        "city": _coverage(staged, "staging_city"),
        "suburb": _coverage(staged, "staging_suburb"),
        "geo_area": _coverage(staged, "staging_geo_area"),
        "cluster": _coverage(staged, "staging_business_cluster"),
    }
    source_counts = staged["staging_source"].value_counts(dropna=False).to_dict()
    return {
        "row_count": len(rows),
        "current": current,
        "staging": staging,
        "delta_pct_points": {
            key: round((staging[key]["rate"] - current[key]["rate"]) * 100, 2)
            for key in current
        },
        "staging_source_counts": source_counts,
    }


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def _by_postcode(df: pd.DataFrame, column: str) -> dict[str, list[dict[str, Any]]]:
    if df.empty or column not in df.columns:
        return {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in df.to_dict("records"):
        postcode = _normalize_postcode(row.get(column))
        if postcode:
            grouped.setdefault(postcode, []).append(row)
    return grouped


def _manual_au_rules(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty or "rule_type" not in df.columns:
        return []
    manual = df[df["rule_type"].astype(str).eq("manual_override")]
    return manual.to_dict("records")


def _suburb_aliases(df: pd.DataFrame, *, country: str) -> list[tuple[str, dict[str, Any]]]:
    if df.empty or "Suburb" not in df.columns:
        return []
    aliases = []
    for row in df.to_dict("records"):
        suburb = _normalize_alias(row.get("Suburb"))
        if not suburb or len(suburb) < (4 if country == "NZ" else 5):
            continue
        aliases.append((suburb, row))
    aliases.sort(key=lambda item: len(item[0]), reverse=True)
    return aliases


def _pick_best_row(rows: list[dict[str, Any]], address: str) -> dict[str, Any]:
    if not rows:
        return {}
    normalized_address = _normalize_alias(address)
    for row in rows:
        suburb = _normalize_alias(row.get("Suburb"))
        if suburb and suburb in normalized_address:
            return row
    return rows[0]


def _find_alias(address: str, aliases: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    normalized = _normalize_alias(address)
    if not normalized:
        return None
    for alias, row in aliases:
        if alias in normalized:
            return row
    return None


def _find_manual_au_rule(address: str, postcode: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_address = _normalize_alias(address)
    for row in rules:
        rule_postcode = _normalize_postcode(row.get("Postcode"))
        suburb = _normalize_alias(row.get("Suburb"))
        if rule_postcode and postcode and rule_postcode == postcode:
            return row
        if suburb and suburb in normalized_address:
            return row
    return None


def _city_from_text(country: str, value: str) -> str:
    normalized = _normalize_alias(value)
    for city, aliases in CITY_ALIASES.get(country, {}).items():
        if any(_contains_token(normalized, alias) for alias in aliases):
            return city
    return ""


def _contains_token(text: str, alias: str) -> bool:
    return bool(alias and re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text))


def _country(row: dict[str, Any]) -> str:
    value = _text(row.get("analysis_country") or row.get("country_group") or row.get("scope_country")).upper()
    if value in {"NZ", "554"}:
        return "NZ"
    if value in {"AU", "036", "36"}:
        return "AU"
    return value


def _coverage(df: pd.DataFrame, column: str) -> dict[str, Any]:
    if column not in df.columns or len(df) == 0:
        return {"count": 0, "rate": 0.0}
    values = df[column].fillna("").astype(str).str.strip()
    covered = values[~values.isin(UNKNOWN_CITY_LABELS)]
    return {"count": int(len(covered)), "rate": round(len(covered) / len(df), 6)}


def _extract_postcode(value: str) -> str:
    matches = re.findall(r"\b(\d{4})\b", _text(value))
    return matches[-1] if matches else ""


def _normalize_postcode(value: Any) -> str:
    digits = re.sub(r"\D+", "", _text(value))
    if len(digits) == 3:
        return digits.zfill(4)
    if len(digits) == 4:
        return digits
    return ""


def _normalize_alias(value: Any) -> str:
    text = _text(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _text(value: Any) -> str:
    return str(value or "").strip()
