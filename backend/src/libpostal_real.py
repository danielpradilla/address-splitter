from __future__ import annotations

from typing import Any

from postal.parser import parse_address


def _pick(parts: list[tuple[str, str]], label: str) -> list[str]:
    return [v for (v, l) in parts if l == label and v]


def parse_with_libpostal(*, recipient_name: str, country_code: str, raw_address: str) -> dict[str, Any]:
    """Parse address using libpostal (Senzing data model baked into image).

    Returns a dict compatible with normalize_result().
    """
    parts = parse_address(raw_address or "") if raw_address else []

    house_number = " ".join(_pick(parts, "house_number")).strip()
    road = " ".join(_pick(parts, "road")).strip()
    unit = " ".join(_pick(parts, "unit")).strip()
    level = " ".join(_pick(parts, "level")).strip()
    po_box = " ".join(_pick(parts, "po_box")).strip()

    city = " ".join(_pick(parts, "city")).strip()
    state = " ".join(_pick(parts, "state")).strip()
    postcode = " ".join(_pick(parts, "postcode")).strip()
    neighborhood = " ".join(_pick(parts, "suburb")).strip() or " ".join(_pick(parts, "neighbourhood")).strip()

    company = " ".join(_pick(parts, "house")).strip() or " ".join(_pick(parts, "building")).strip()

    address_line1 = " ".join([x for x in [road, house_number] if x]).strip()
    if not address_line1:
        address_line1 = " ".join(_pick(parts, "house")).strip() or ""

    # Put unit/level into line2
    address_line2 = ", ".join([x for x in [unit, level] if x]).strip()

    warnings: list[str] = []
    if not parts:
        warnings.append("libpostal_no_parse")

    # very rough confidence heuristic
    conf = 0.4
    if address_line1:
        conf += 0.25
    if city:
        conf += 0.15
    if postcode:
        conf += 0.15
    if conf > 0.95:
        conf = 0.95

    return {
        "recipient_name": recipient_name or "",
        "country_code": (country_code or "").strip().upper(),
        "address_line1": address_line1,
        "address_line2": address_line2,
        "postcode": postcode,
        "city": city,
        "state_region": state,
        "neighborhood": neighborhood,
        "po_box": po_box,
        "company": company,
        "attention": "",
        "raw_address": raw_address or "",
        "confidence": conf,
        "warnings": warnings,
        "libpostal_parts": parts,
    }
