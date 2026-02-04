from __future__ import annotations

from typing import Any

import boto3


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


def lookup_city_best(*, cities_table: str, country_code: str, city: str) -> dict[str, Any] | None:
    if not cities_table or not country_code or not city:
        return None
    cc = country_code.strip().upper()
    city_key = city.strip().lower()
    pk = f"{cc}#{city_key}"

    table = boto3.resource("dynamodb").Table(cities_table)
    resp = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq(pk),
        ScanIndexForward=False,
        Limit=1,
    )
    items = resp.get("Items") or []
    return items[0] if items else None


def lookup_city_to_postcode(*, postcodes_table: str, country_code: str, city: str) -> dict[str, Any] | None:
    """Find any postcode row matching city name via GSI2 (CC#citylower)."""
    if not postcodes_table or not country_code or not city:
        return None
    cc = country_code.strip().upper()
    city_key = city.strip().lower()
    gsi_pk = f"{cc}#{city_key}"

    table = boto3.resource("dynamodb").Table(postcodes_table)
    resp = table.query(
        IndexName="GSI2",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("GSI2PK").eq(gsi_pk),
        ScanIndexForward=True,
        Limit=1,
    )
    items = resp.get("Items") or []
    return items[0] if items else None
