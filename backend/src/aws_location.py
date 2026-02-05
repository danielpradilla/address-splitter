import boto3

try:
    from iso3166 import countries as _iso_countries
except Exception:  # pragma: no cover
    _iso_countries = None


def _to_iso3(country: str) -> str | None:
    if not country:
        return None
    c = country.strip().upper()
    if len(c) == 3:
        return c
    if len(c) == 2 and _iso_countries is not None:
        try:
            return _iso_countries.get(c).alpha3
        except Exception:
            return None
    return None


def geocode_with_amazon_location(*, place_index_name: str, text: str, country: str | None = None, region: str | None = None) -> dict:
    """Return a normalized geocoding result from Amazon Location Service.

    This is intended for pipeline `aws_services`.

    Returns:
      {
        latitude, longitude,
        geo_accuracy,
        raw: <provider response excerpt>,
        components: {address_line1, postcode, city, state_region, country_code}
      }
    """
    client = boto3.client("location", region_name=region)

    params = {
        "IndexName": place_index_name,
        "Text": text,
        "MaxResults": 1,
    }
    # Amazon Location expects ISO-3 filter countries; UI/app uses ISO-2.
    iso3 = _to_iso3(country or "")
    if iso3:
        params["FilterCountries"] = [iso3]

    resp = client.search_place_index_for_text(**params)
    results = resp.get("Results") or []
    if not results:
        return {
            "geo_accuracy": "none",
            "warnings": ["no_location_match"],
        }

    place = (results[0] or {}).get("Place") or {}
    geom = place.get("Geometry") or {}
    point = geom.get("Point") or []
    # Point is [lon, lat]
    lon = point[0] if len(point) > 0 else None
    lat = point[1] if len(point) > 1 else None

    # Provider components
    postal = place.get("PostalCode") or ""
    municipality = place.get("Municipality") or ""
    region_name = place.get("Region") or ""
    country_code = place.get("Country") or (country or "")
    label = place.get("Label") or ""

    # Very rough component mapping (good enough for v1)
    address_line1 = label
    city = municipality
    state_region = region_name

    geo_accuracy = "street" if (place.get("Street") or place.get("AddressNumber")) else "city"

    out = {
        "latitude": lat,
        "longitude": lon,
        "geo_accuracy": geo_accuracy,
        "geonames_match": "",
        "components": {
            "address_line1": address_line1,
            "address_line2": "",
            "postcode": postal,
            "city": city,
            "state_region": state_region,
            "country_code": country_code,
        },
        "raw": {
            "label": label,
            "street": place.get("Street"),
            "address_number": place.get("AddressNumber"),
            "postal_code": postal,
            "municipality": municipality,
            "region": region_name,
            "country": country_code,
        },
    }
    return out
