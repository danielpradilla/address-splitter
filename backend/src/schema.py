from typing import Any


REQUIRED_KEYS = [
    "country_code",
    "raw_address",
    "confidence",
    "warnings",
]

ALL_KEYS = [
    "country_code",
    "address_line1",
    "address_line2",
    "postcode",
    "city",
    "state_region",
    "neighborhood",
    "po_box",
    "company",
    "attention",
    "raw_address",
    "confidence",
    "warnings",
]


def normalize_result(obj: dict[str, Any], *, fallback: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    for k in ALL_KEYS:
        if k in ("confidence", "warnings"):
            continue
        v = obj.get(k)
        if v is None:
            v = ""
        if not isinstance(v, str):
            v = str(v)
        out[k] = v.strip()

    # Ensure required fallbacks
    out["raw_address"] = out.get("raw_address") or fallback.get("raw_address", "")

    # Country
    out["country_code"] = (out.get("country_code") or fallback.get("country_code") or "").strip().upper()

    # confidence
    conf = obj.get("confidence")
    try:
        conf_f = float(conf)
    except Exception:
        conf_f = 0.0
    if conf_f < 0:
        conf_f = 0.0
    if conf_f > 1:
        conf_f = 1.0
    out["confidence"] = conf_f

    # warnings
    warnings = obj.get("warnings")
    if isinstance(warnings, list):
        out["warnings"] = [str(w).strip() for w in warnings if str(w).strip()]
    elif warnings is None:
        out["warnings"] = []
    else:
        out["warnings"] = [str(warnings).strip()] if str(warnings).strip() else []

    return out
