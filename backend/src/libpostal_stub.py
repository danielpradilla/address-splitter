from __future__ import annotations

import re
from typing import Any


_POSTCODE_CITY_RE = re.compile(r"^(?P<postcode>[A-Za-z0-9][A-Za-z0-9\- ]{2,10})\s+(?P<city>.+)$")


def parse_address_stub(*, recipient_name: str, country_code: str, raw_address: str) -> dict[str, Any]:
    """Very small libpostal-like parser.

    This is a pragmatic fallback until we package libpostal properly.

    Heuristics:
    - Split on newlines/commas, trim blanks.
    - address_line1: first chunk
    - try to parse a chunk containing "<postcode> <city>" (common in EU)
    - remaining chunk(s): address_line2 / state_region (best-effort)
    """

    chunks = [c.strip() for c in re.split(r"[\n\r]+", raw_address or "") if c.strip()]
    # also split long single-line addresses by commas
    if len(chunks) <= 1:
        chunks = [c.strip() for c in (raw_address or "").split(",") if c.strip()]

    out = {
        "recipient_name": recipient_name or "",
        "country_code": (country_code or "").strip().upper(),
        "address_line1": "",
        "address_line2": "",
        "postcode": "",
        "city": "",
        "state_region": "",
        "neighborhood": "",
        "po_box": "",
        "company": "",
        "attention": "",
        "raw_address": raw_address or "",
        "confidence": 0.55 if raw_address else 0.0,
        "warnings": ["libpostal_stub"],
    }

    if not chunks:
        return out

    out["address_line1"] = chunks[0]

    # Search from the end for a postcode+city line
    for idx in range(len(chunks) - 1, -1, -1):
        m = _POSTCODE_CITY_RE.match(chunks[idx])
        if not m:
            continue
        pc = (m.group("postcode") or "").strip()
        city = (m.group("city") or "").strip()
        # Avoid matching e.g. street numbers: require postcode-like token length >= 4
        if len(re.sub(r"\s+", "", pc)) < 4:
            continue
        out["postcode"] = pc
        out["city"] = city
        # Anything between line1 and this line becomes address_line2
        mid = [c for i, c in enumerate(chunks[1:idx]) if c]
        if mid:
            out["address_line2"] = ", ".join(mid)
        break

    # If we didn't find postcode/city, try last chunk as city (common when postcode omitted)
    if not out["city"] and len(chunks) >= 2:
        out["city"] = chunks[-1]

    return out
