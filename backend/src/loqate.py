import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


DEFAULT_BASE_URL = "https://api.addressy.com"


def _get_base_url() -> str:
    return (os.getenv("LOQATE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _get_api_key() -> str:
    k = (os.getenv("LOQATE_API_KEY") or "").strip()
    if not k:
        raise ValueError("missing_loqate_api_key")
    return k


def _http_get_json(url: str, timeout_s: float = 8.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw)
    except Exception as e:
        raise ValueError(f"loqate_invalid_json: {e}")


def loqate_find(*,
    text: str,
    country_code: str = "",
    limit: int = 5,
    language: str = "",
    timeout_s: float = 8.0,
) -> Dict[str, Any]:
    """Loqate Capture Interactive Find.

    Returns the raw JSON payload.
    """
    key = _get_api_key()
    base = _get_base_url()

    params = {
        "Key": key,
        "Text": text,
        "Limit": str(max(1, min(int(limit), 10))),
    }

    # Intentionally do NOT pass Countries filter.
    # Rationale: keep behavior consistent with the other pipelines (global search).
    # If you later want to enable filtering, add a separate flag/env toggle.

    if language:
        params["Language"] = language

    url = f"{base}/Capture/Interactive/Find/v1.10/json3.ws?{urllib.parse.urlencode(params)}"
    return _http_get_json(url, timeout_s=timeout_s)


def loqate_retrieve(*,
    item_id: str,
    timeout_s: float = 8.0,
) -> Dict[str, Any]:
    """Loqate Capture Interactive Retrieve.

    Returns the raw JSON payload.
    """
    key = _get_api_key()
    base = _get_base_url()

    params = {
        "Key": key,
        "Id": item_id,
    }
    url = f"{base}/Capture/Interactive/Retrieve/v1.00/json3.ws?{urllib.parse.urlencode(params)}"
    return _http_get_json(url, timeout_s=timeout_s)


def resolve_address(*,
    raw_address: str,
    country_code: str = "",
    language: str = "",
    timeout_s: float = 8.0,
) -> Dict[str, Any]:
    """Resolve a free-text address into structured components via Find -> Retrieve.

    Output: dict shaped like the repo's normalize_result schema keys plus extra fields.
    """
    raw_address = (raw_address or "").strip()
    if not raw_address:
        raise ValueError("missing_raw_address")

    find = loqate_find(text=raw_address, country_code=country_code, language=language, timeout_s=timeout_s)
    items = find.get("Items") or []
    if not items:
        return {
            "country_code": country_code or "",
            "raw_address": raw_address,
            "confidence": 0.0,
            "warnings": ["loqate_no_candidates"],
            "raw": {"best": None},
        }

    best = items[0] or {}
    best_id = (best.get("Id") or "").strip()
    if not best_id:
        return {
            "country_code": country_code or "",
            "raw_address": raw_address,
            "confidence": 0.0,
            "warnings": ["loqate_missing_id"],
            "raw": {"best": {"Text": best.get("Text"), "Type": best.get("Type")}},
        }

    retrieve = loqate_retrieve(item_id=best_id, timeout_s=timeout_s)
    r_items = retrieve.get("Items") or []
    if not r_items:
        return {
            "country_code": country_code or "",
            "raw_address": raw_address,
            "confidence": 0.0,
            "warnings": ["loqate_retrieve_empty"],
            "raw": {"best": {"Id": best_id, "Text": best.get("Text"), "Type": best.get("Type")}},
        }

    r0 = r_items[0] or {}

    # Loqate component keys vary by country. Common ones include:
    #  - Line1/Line2/Line3/Line4/Line5
    #  - City, Province/State, PostalCode, CountryIso2
    cc = (r0.get("CountryIso2") or r0.get("CountryISO2") or r0.get("Country") or "").strip().upper()
    if not cc:
        cc = (country_code or "").strip().upper()

    line1 = (r0.get("Line1") or "").strip()
    line2 = (r0.get("Line2") or "").strip()
    # If Line2 empty, try to combine further lines into line2 to avoid losing info.
    extras = [
        (r0.get("Line3") or "").strip(),
        (r0.get("Line4") or "").strip(),
        (r0.get("Line5") or "").strip(),
    ]
    extras = [x for x in extras if x]
    if not line2 and extras:
        line2 = ", ".join(extras)

    city = (r0.get("City") or r0.get("Locality") or "").strip()
    state_region = (r0.get("Province") or r0.get("State") or r0.get("AdministrativeArea") or "").strip()
    postcode = (r0.get("PostalCode") or r0.get("Postcode") or "").strip()

    # Confidence: Loqate doesn't expose a standard [0..1] here; we treat success as high-ish.
    conf = 0.9 if line1 or city or postcode else 0.6

    # NOTE: Do not return full raw provider payloads by default (can be very large).
    return {
        "country_code": cc,
        "address_line1": line1,
        "address_line2": line2,
        "postcode": postcode,
        "city": city,
        "state_region": state_region,
        "neighborhood": "",
        "po_box": "",
        "company": "",
        "attention": "",
        "raw_address": raw_address,
        "confidence": conf,
        "warnings": [],
        "raw": {
            "best": {
                "Id": best_id,
                "Text": best.get("Text"),
                "Type": best.get("Type"),
            }
        },
    }
