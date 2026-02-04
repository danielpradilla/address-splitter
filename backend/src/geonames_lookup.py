from __future__ import annotations

from typing import Any

import math
import re
import unicodedata

import boto3
from boto3.dynamodb.conditions import Key


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9\s]")


def _normalize_name(s: str) -> str:
    """Normalize place/city names for robust matching.

    - casefold + trim
    - ASCII folding (strip accents)
    - remove punctuation
    - collapse whitespace
    """
    if not s:
        return ""
    s = s.strip().casefold()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _pk(country_code: str, postcode: str) -> str:
    return f"{country_code.upper()}#{postcode.strip()}"


def lookup_postcode(*, table_name: str, country_code: str, postcode: str) -> dict[str, Any] | None:
    """Lookup a postcode centroid from offline GeoNames data stored in DynamoDB.

    Table key: PK = "CC#POSTCODE".

    Returns a dict with latitude/longitude (strings) and optional place/admin info.
    """
    if not table_name or not country_code or not postcode:
        return None

    table = boto3.resource("dynamodb").Table(table_name)
    resp = table.get_item(Key={"PK": _pk(country_code, postcode)})
    return resp.get("Item")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Earth radius
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _to_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(str(v))
    except Exception:
        return None


def lookup_city_best(*, cities_table: str, country_code: str, city: str) -> dict[str, Any] | None:
    """Return the most populated city match for (country, city).

    Table PK convention: "CC#<normalized-city>"; SK is population-sorted.
    """
    if not cities_table or not country_code or not city:
        return None

    cc = country_code.strip().upper()
    keys = [_normalize_name(city), city.strip().lower()]
    keys = [k for k in keys if k]

    table = boto3.resource("dynamodb").Table(cities_table)
    for city_key in keys:
        pk = f"{cc}#{city_key}"
        resp = table.query(
            KeyConditionExpression=Key("PK").eq(pk),
            ScanIndexForward=False,
            Limit=1,
        )
        items = resp.get("Items") or []
        if items:
            return items[0]
    return None


def lookup_city_to_postcode_best(
    *,
    postcodes_table: str,
    country_code: str,
    city: str,
    city_lat: Any | None = None,
    city_lon: Any | None = None,
    limit: int = 50,
) -> dict[str, Any] | None:
    """Infer a postcode from (country, city).

    Queries the postcodes table GSI2 by normalized city name. If multiple postcodes
    match, pick the postcode centroid closest to the selected city centroid.

    If city coordinates are missing, returns the first match (sorted by postcode).
    """
    if not postcodes_table or not country_code or not city:
        return None

    cc = country_code.strip().upper()
    keys = [_normalize_name(city), city.strip().lower()]
    keys = [k for k in keys if k]

    table = boto3.resource("dynamodb").Table(postcodes_table)

    def _query(gsi_pk: str) -> list[dict[str, Any]]:
        resp = table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key("GSI2PK").eq(gsi_pk),
            ScanIndexForward=True,
            Limit=limit,
        )
        return resp.get("Items") or []

    items: list[dict[str, Any]] = []
    for k in keys:
        items = _query(f"{cc}#{k}")
        if items:
            break
    if not items:
        return None

    lat0 = _to_float(city_lat)
    lon0 = _to_float(city_lon)
    if lat0 is None or lon0 is None or len(items) == 1:
        return items[0]

    best = None
    best_d = None
    for it in items:
        lat = _to_float(it.get("latitude"))
        lon = _to_float(it.get("longitude"))
        if lat is None or lon is None:
            continue
        d = _haversine_km(lat0, lon0, lat, lon)
        if best is None or (best_d is not None and d < best_d) or best_d is None:
            best = it
            best_d = d

    return best or items[0]
