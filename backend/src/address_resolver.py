import json
import os
import time
from typing import Any

from aws_location import geocode_with_amazon_location
from bedrock_invoke import invoke_bedrock_json
from cost import estimate_bedrock_cost_usd, estimate_location_cost_usd
from geonames_lookup import lookup_city_best, lookup_city_to_postcode_best, lookup_postcode
from loqate import resolve_address as loqate_resolve_address
from schema import normalize_result


DEFAULT_PIPELINES = [
    "bedrock_geonames",
    "libpostal_geonames",
    "aws_services",
    "loqate",
]


def _enrich_with_geonames(
    *,
    norm: dict[str, Any],
    geonames_table: str,
    geonames_cities: str,
) -> dict[str, Any]:
    if geonames_table and norm.get("country_code") and norm.get("postcode"):
        hit = lookup_postcode(
            table_name=geonames_table,
            country_code=norm.get("country_code", ""),
            postcode=norm.get("postcode", ""),
        )
        if hit and hit.get("latitude") and hit.get("longitude"):
            norm["latitude"] = hit.get("latitude")
            norm["longitude"] = hit.get("longitude")
            norm["geo_accuracy"] = "postcode"
            norm["geonames_match"] = f"{hit.get('place_name', '')} {hit.get('postcode', '')}".strip()

    if (
        geonames_table
        and not norm.get("postcode")
        and norm.get("country_code")
        and norm.get("city")
    ):
        city_best = (
            lookup_city_best(
                cities_table=geonames_cities,
                country_code=norm.get("country_code", ""),
                city=norm.get("city", ""),
            )
            if geonames_cities
            else None
        )

        if city_best and city_best.get("latitude") and city_best.get("longitude"):
            norm["latitude"] = city_best.get("latitude")
            norm["longitude"] = city_best.get("longitude")
            norm["geo_accuracy"] = "city"
            norm["geonames_match"] = f"{city_best.get('name', '')}".strip()

        pc_hit = lookup_city_to_postcode_best(
            postcodes_table=geonames_table,
            country_code=norm.get("country_code", ""),
            city=norm.get("city", ""),
            city_lat=city_best.get("latitude") if city_best else None,
            city_lon=city_best.get("longitude") if city_best else None,
            limit=50,
        )
        if pc_hit and pc_hit.get("postcode"):
            norm["postcode"] = pc_hit.get("postcode")
            norm["geonames_match"] = f"{pc_hit.get('place_name', '')} {pc_hit.get('postcode', '')}".strip()
            if not norm.get("latitude") and pc_hit.get("latitude") and pc_hit.get("longitude"):
                norm["latitude"] = pc_hit.get("latitude")
                norm["longitude"] = pc_hit.get("longitude")
                norm["geo_accuracy"] = "postcode"

    return norm


def resolve_address(
    *,
    country_code: str,
    raw_address: str,
    model_id: str,
    pipelines: list[str] | None,
    rendered_prompt: str,
    pricing: dict[str, Any] | None,
    region: str | None = None,
    geonames_table: str | None = None,
    geonames_cities: str | None = None,
    place_index: str | None = None,
    loqate_language: str | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    pricing = pricing or {}
    geonames_table = geonames_table or ""
    geonames_cities = geonames_cities or ""
    place_index = place_index or ""
    loqate_language = loqate_language or ""

    for pipeline in pipelines or DEFAULT_PIPELINES:
        if pipeline == "bedrock_geonames":
            if not model_id:
                results[pipeline] = {
                    "source": "bedrock",
                    "geocode": "geonames_offline",
                    "warnings": ["missing_modelId"],
                    "confidence": 0.0,
                }
                continue

            try:
                parsed = invoke_bedrock_json(
                    model_id=model_id,
                    prompt=rendered_prompt,
                    region=region,
                )
                norm = normalize_result(
                    parsed,
                    fallback={
                        "country_code": country_code,
                        "raw_address": raw_address,
                    },
                )
                norm = _enrich_with_geonames(
                    norm=norm,
                    geonames_table=geonames_table,
                    geonames_cities=geonames_cities,
                )
                out_text = json.dumps(parsed)
                in_rate = float(pricing.get("bedrock_input_usd_per_million") or 0)
                out_rate = float(pricing.get("bedrock_output_usd_per_million") or 0)
                cost = estimate_bedrock_cost_usd(
                    prompt=rendered_prompt,
                    output_text=out_text,
                    in_per_m=in_rate,
                    out_per_m=out_rate,
                )
                norm.update(
                    {
                        "source": "bedrock",
                        "geocode": "geonames_offline",
                        "rendered_prompt": rendered_prompt,
                        "cost": cost,
                    }
                )
                results[pipeline] = norm
            except Exception as e:
                msg = str(e)
                warnings = ["bedrock_invoke_failed"]
                if "inference profile" in msg.lower():
                    warnings.append("requires_inference_profile")
                warnings.append(msg)
                results[pipeline] = {
                    "source": "bedrock",
                    "geocode": "geonames_offline",
                    "rendered_prompt": rendered_prompt,
                    "warnings": warnings,
                    "confidence": 0.0,
                }
        elif pipeline == "libpostal_geonames":
            try:
                pipeline_t0 = time.perf_counter()
                print("[timing] pipeline=libpostal_geonames step=before_import", flush=True)
                step_t0 = time.perf_counter()
                from libpostal_real import parse_with_libpostal

                print(
                    "[timing] pipeline=libpostal_geonames step=import_libpostal "
                    f"ms={(time.perf_counter() - step_t0) * 1000:.1f}",
                    flush=True,
                )

                step_t0 = time.perf_counter()
                parsed = parse_with_libpostal(
                    country_code=country_code,
                    raw_address=raw_address,
                )
                print(
                    "[timing] pipeline=libpostal_geonames step=parse_with_libpostal "
                    f"ms={(time.perf_counter() - step_t0) * 1000:.1f} "
                    f"parts={len(parsed.get('libpostal_parts', []))}",
                    flush=True,
                )

                step_t0 = time.perf_counter()
                norm = normalize_result(
                    parsed,
                    fallback={
                        "country_code": country_code,
                        "raw_address": raw_address,
                    },
                )
                print(
                    "[timing] pipeline=libpostal_geonames step=normalize_result "
                    f"ms={(time.perf_counter() - step_t0) * 1000:.1f}",
                    flush=True,
                )

                norm = _enrich_with_geonames(
                    norm=norm,
                    geonames_table=geonames_table,
                    geonames_cities=geonames_cities,
                )
                norm.update(
                    {
                        "source": "libpostal",
                        "geocode": "geonames_offline",
                        "libpostal_parts": parsed.get("libpostal_parts", []),
                    }
                )
                print(
                    "[timing] pipeline=libpostal_geonames step=total "
                    f"ms={(time.perf_counter() - pipeline_t0) * 1000:.1f}",
                    flush=True,
                )
                results[pipeline] = norm
            except Exception as e:
                results[pipeline] = {
                    "source": "libpostal",
                    "geocode": "geonames_offline",
                    "warnings": ["libpostal_failed", str(e)],
                    "confidence": 0.0,
                }
        elif pipeline == "aws_services":
            if not place_index:
                results[pipeline] = {
                    "source": "amazon_location",
                    "geocode": "amazon_location",
                    "warnings": ["missing_place_index"],
                    "confidence": 0.0,
                }
                continue

            try:
                geo = geocode_with_amazon_location(
                    place_index_name=place_index,
                    text=raw_address,
                    country=country_code,
                    region=region,
                )
                comp = geo.get("components") or {}
                per_req = float(pricing.get("location_usd_per_request") or 0)
                cost = estimate_location_cost_usd(per_request=per_req)
                results[pipeline] = {
                    "source": "amazon_location",
                    "geocode": "amazon_location",
                    "warnings": geo.get("warnings") or [],
                    "confidence": 0.8 if (geo.get("latitude") is not None and geo.get("longitude") is not None) else 0.0,
                    "latitude": geo.get("latitude"),
                    "longitude": geo.get("longitude"),
                    "geo_accuracy": geo.get("geo_accuracy", "none"),
                    "address_line1": comp.get("address_line1", ""),
                    "address_line2": comp.get("address_line2", ""),
                    "postcode": comp.get("postcode", ""),
                    "city": comp.get("city", ""),
                    "state_region": comp.get("state_region", ""),
                    "country_code": comp.get("country_code", country_code),
                    "raw": geo.get("raw"),
                    "cost": cost,
                }
            except Exception as e:
                results[pipeline] = {
                    "source": "amazon_location",
                    "geocode": "amazon_location",
                    "warnings": ["amazon_location_failed", str(e)],
                    "confidence": 0.0,
                }
        elif pipeline == "loqate":
            try:
                out = loqate_resolve_address(
                    raw_address=raw_address,
                    country_code=country_code,
                    language=loqate_language,
                )
                norm = normalize_result(
                    out,
                    fallback={
                        "country_code": country_code,
                        "raw_address": raw_address,
                    },
                )
                norm.update(
                    {
                        "source": "loqate",
                        "geocode": "none",
                        "raw": out.get("raw"),
                    }
                )
                results[pipeline] = norm
            except Exception as e:
                results[pipeline] = {
                    "source": "loqate",
                    "geocode": "none",
                    "warnings": ["loqate_failed", str(e)],
                    "confidence": 0.0,
                }

    return results


def corrected_address_full(result: dict[str, Any]) -> str:
    parts = [
        result.get("address_line1", ""),
        result.get("address_line2", ""),
        result.get("postcode", ""),
        result.get("city", ""),
        result.get("state_region", ""),
        result.get("country_code", ""),
    ]
    return ", ".join(part for part in parts if str(part).strip())


def choose_best_pipeline(results: dict[str, Any]) -> str:
    best_name = ""
    best_score = -1.0
    for name, result in results.items():
        try:
            score = float(result.get("confidence") or 0.0)
        except Exception:
            score = 0.0
        if score > best_score:
            best_name = name
            best_score = score
    return best_name


def allowed_pipelines() -> set[str]:
    return set(DEFAULT_PIPELINES)


def default_pipelines() -> list[str]:
    return list(DEFAULT_PIPELINES)


def build_runtime_config_from_env() -> dict[str, str]:
    return {
        "region": os.getenv("AWS_REGION_NAME"),
        "geonames_table": os.getenv("GEONAMES_TABLE", ""),
        "geonames_cities": os.getenv("GEONAMES_CITIES_TABLE", ""),
        "place_index": os.getenv("PLACE_INDEX_NAME", ""),
        "loqate_language": os.getenv("LOQATE_LANGUAGE", ""),
    }
