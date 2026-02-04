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
