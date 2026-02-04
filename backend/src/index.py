import json
import os
import time
from typing import Any, Dict

import boto3

from aws_location import geocode_with_amazon_location
from bedrock_invoke import invoke_bedrock_json
from models import list_bedrock_models
from prompting import render_prompt, validate_template
from cost import estimate_bedrock_cost_usd, estimate_location_cost_usd
from geonames_lookup import lookup_city_best, lookup_city_to_postcode, lookup_postcode
from schema import normalize_result
from storage import epoch_plus_days, get_submission, list_recent, put_submission, set_preferred, user_settings_table
from ulid_util import new_ulid


ddb = boto3.resource("dynamodb")


def _cors_headers() -> Dict[str, str]:
    origin = os.getenv("ALLOWED_ORIGINS", "*")
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "authorization,content-type",
        "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
    }


def _resp(status: int, body: Any):
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps(body)}


def _get_user_sub(event: dict) -> str:
    # HTTP API JWT authorizer puts claims here.
    claims = (
        (event.get("requestContext") or {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    sub = claims.get("sub")
    if not sub:
        raise ValueError("missing_jwt_sub")
    return sub


def handler(event, context):
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method", "")
    route_key = (event.get("requestContext") or {}).get("routeKey", "")

    if method == "OPTIONS":
        # CORS preflight
        return {"statusCode": 204, "headers": _cors_headers(), "body": ""}

    if route_key == "GET /health":
        return _resp(200, {"ok": True, "ts": int(time.time())})

    # Everything else requires auth (API GW already enforces), but we still read sub.
    try:
        user_sub = _get_user_sub(event)
    except Exception:
        return _resp(401, {"error": "unauthorized"})

    # Prompt settings
    if route_key == "GET /prompt":
        table_name = os.getenv("USER_SETTINGS_TABLE", "")
        if not table_name:
            return _resp(500, {"error": "missing_config", "field": "USER_SETTINGS_TABLE"})
        table = ddb.Table(table_name)
        item = table.get_item(Key={"user_sub": user_sub}).get("Item")
        if item and item.get("prompt_template"):
            return _resp(
                200,
                {
                    "prompt_template": item["prompt_template"],
                    "is_default": False,
                    "pricing": item.get("pricing") or {},
                },
            )

        # Default demo prompt
        demo = """You are an expert postal address parser and normalizer.

Goal:
- Parse the free-text address and return a single JSON object with the required fields.
- If {country} is provided, use it as the authoritative country context.
- If {country} is empty, infer the most likely country from the address text.

Input:
- Recipient name: {name}
- Country context (ISO-2, may be empty): {country}
- Address (free text):
{address}

Output rules (VERY IMPORTANT):
- Return ONLY valid JSON. No markdown, no comments, no extra keys.
- Use empty string \"\" for unknown fields.
- confidence must be a number between 0 and 1.
- warnings must be an array of strings.

Return JSON with exactly these keys:
recipient_name, country_code, address_line1, address_line2, postcode, city, state_region, neighborhood, po_box, company, attention, raw_address, confidence, warnings
"""
        # Default pricing estimates (USD)
        pricing = {
            "bedrock_input_usd_per_million": 3.0,
            "bedrock_output_usd_per_million": 15.0,
            "location_usd_per_request": 0.005,
        }
        return _resp(200, {"prompt_template": demo, "is_default": True, "pricing": pricing})

    if route_key == "PUT /prompt":
        table_name = os.getenv("USER_SETTINGS_TABLE", "")
        if not table_name:
            return _resp(500, {"error": "missing_config", "field": "USER_SETTINGS_TABLE"})
        body = event.get("body") or "{}"
        try:
            data = json.loads(body)
        except Exception:
            return _resp(400, {"error": "invalid_json"})
        prompt = (data.get("prompt_template") or "").strip()
        if "{address}" not in prompt:
            return _resp(400, {"error": "invalid_prompt", "message": "prompt_template must include {address}"})

        table = ddb.Table(table_name)
        pricing = data.get("pricing")
        item = {
            "user_sub": user_sub,
            "prompt_template": prompt,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if isinstance(pricing, dict):
            item["pricing"] = pricing

        table.put_item(Item=item)
        return _resp(200, {"ok": True})

    if route_key == "GET /models":
        try:
            region = os.getenv("AWS_REGION_NAME")
            profiles = []
            profiles_error = ""
            try:
                from models import list_inference_profiles
                profiles = list_inference_profiles(region=region)
            except Exception as e:
                profiles_error = str(e)
                profiles = []

            models = list_bedrock_models(region=region)
            resp = {"inference_profiles": profiles, "models": models}
            if profiles_error:
                resp["inference_profiles_error"] = profiles_error
            return _resp(200, resp)
        except Exception as e:
            return _resp(500, {"error": "bedrock_list_failed", "message": str(e)})

    if route_key == "GET /recent":
        table_name = os.getenv("SUBMISSIONS_TABLE", "")
        if not table_name:
            return _resp(500, {"error": "missing_config", "field": "SUBMISSIONS_TABLE"})

        params = event.get("queryStringParameters") or {}
        try:
            limit = int(params.get("limit") or 10)
        except Exception:
            limit = 10
        limit = max(1, min(limit, 10))

        try:
            items = list_recent(table_name=table_name, user_sub=user_sub, limit=limit)
            # Return a preview list including per-pipeline summaries (for 3-column recent UI)
            out = []
            for it in items:
                inp = it.get("input") or {}
                res = it.get("results") or {}

                def _summ(r: dict | None):
                    r = r or {}
                    return {
                        "address_line1": r.get("address_line1", ""),
                        "postcode": r.get("postcode", ""),
                        "city": r.get("city", ""),
                        "geo_accuracy": r.get("geo_accuracy", ""),
                        "latitude": r.get("latitude"),
                        "longitude": r.get("longitude"),
                        "warnings": r.get("warnings") or [],
                    }

                out.append(
                    {
                        "submission_id": it.get("submission_id"),
                        "created_at": it.get("created_at"),
                        "country_code": inp.get("country_code"),
                        "recipient_name": inp.get("recipient_name"),
                        "raw_address_preview": (inp.get("raw_address") or "").replace("\n", ", ")[:120],
                        "preferred_method": it.get("preferred_method"),
                        "pipelines": {
                            "bedrock_geonames": _summ(res.get("bedrock_geonames")),
                            "libpostal_geonames": _summ(res.get("libpostal_geonames")),
                            "aws_services": _summ(res.get("aws_services")),
                        },
                    }
                )
            return _resp(200, {"items": out})
        except Exception as e:
            return _resp(500, {"error": "recent_failed", "message": str(e)})

    if route_key == "GET /submission/{id}":
        table_name = os.getenv("SUBMISSIONS_TABLE", "")
        if not table_name:
            return _resp(500, {"error": "missing_config", "field": "SUBMISSIONS_TABLE"})
        submission_id = (event.get("pathParameters") or {}).get("id")
        if not submission_id:
            return _resp(400, {"error": "missing_id"})

        item = get_submission(table_name=table_name, user_sub=user_sub, submission_id=submission_id)
        if not item:
            return _resp(404, {"error": "not_found"})
        return _resp(200, item)

    if route_key == "PUT /submission/{id}/preferred":
        table_name = os.getenv("SUBMISSIONS_TABLE", "")
        if not table_name:
            return _resp(500, {"error": "missing_config", "field": "SUBMISSIONS_TABLE"})
        submission_id = (event.get("pathParameters") or {}).get("id")
        if not submission_id:
            return _resp(400, {"error": "missing_id"})

        body = event.get("body") or "{}"
        try:
            data = json.loads(body)
        except Exception:
            return _resp(400, {"error": "invalid_json"})

        preferred = (data.get("preferred_method") or "").strip()
        allowed = {"bedrock_geonames", "libpostal_geonames", "aws_services"}
        if preferred not in allowed:
            return _resp(400, {"error": "invalid_preferred_method", "allowed": sorted(list(allowed))})

        set_preferred(table_name=table_name, user_sub=user_sub, submission_id=submission_id, preferred_method=preferred)
        return _resp(200, {"ok": True})

    if route_key == "POST /split":
        # For now: create a submission and store placeholder results for all requested pipelines.
        # Next step: implement the real pipeline logic.
        table_name = os.getenv("SUBMISSIONS_TABLE", "")
        settings_table_name = os.getenv("USER_SETTINGS_TABLE", "")
        if not table_name or not settings_table_name:
            return _resp(500, {"error": "missing_config"})

        body = event.get("body") or "{}"
        try:
            data = json.loads(body)
        except Exception:
            return _resp(400, {"error": "invalid_json"})

        recipient_name = (data.get("recipient_name") or "").strip()
        country_code = (data.get("country_code") or "").strip().upper()
        raw_address = (data.get("raw_address") or "").strip()
        model_id = (data.get("modelId") or "").strip()
        pipelines = data.get("pipelines") or ["bedrock_geonames", "libpostal_geonames", "aws_services"]

        if not recipient_name or not raw_address:
            return _resp(400, {"error": "missing_fields", "required": ["recipient_name","raw_address"], "optional": ["country_code"]})

        if not country_code:
            # v1 behavior: allow empty country (auto-detect to be implemented in pipeline #1 later).
            country_code = ""

        # prompt render (for future use)
        prompt_t = user_settings_table(settings_table_name).get_item(Key={"user_sub": user_sub}).get("Item", {}).get("prompt_template")
        if not prompt_t:
            prompt_t = "Take the {country} and split the following address: {address}. Return ONLY JSON."
        try:
            validate_template(prompt_t)
        except Exception as e:
            return _resp(400, {"error": "invalid_prompt", "message": str(e)})
        rendered_prompt = render_prompt(prompt_t, name=recipient_name, country=country_code, address=raw_address)

        # Pricing settings (optional)
        pricing = user_settings_table(settings_table_name).get_item(Key={"user_sub": user_sub}).get("Item", {}).get("pricing") or {}

        submission_id = new_ulid()
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ttl = epoch_plus_days(int(os.getenv("RESULTS_RETENTION_DAYS", "30")))

        results = {}
        for p in pipelines:
            if p == "bedrock_geonames":
                if not model_id:
                    results[p] = {
                        "source": "bedrock",
                        "geocode": "geonames_offline",
                        "warnings": ["missing_modelId"],
                        "confidence": 0.0,
                    }
                else:
                    try:
                        parsed = invoke_bedrock_json(
                            model_id=model_id,
                            prompt=rendered_prompt,
                            region=os.getenv("AWS_REGION_NAME"),
                        )
                        norm = normalize_result(
                            parsed,
                            fallback={
                                "recipient_name": recipient_name,
                                "country_code": country_code,
                                "raw_address": raw_address,
                            },
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

                        # GeoNames enrichment
                        geonames_table = os.getenv("GEONAMES_TABLE", "")
                        geonames_cities = os.getenv("GEONAMES_CITIES_TABLE", "")

                        # 1) Prefer postcode centroid
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
                                norm["geonames_match"] = f"{hit.get('place_name','')} {hit.get('postcode','')}".strip()

                        # 2) If no postcode but have city+country, pick most populated city match and try to infer postcode
                        if (
                            geonames_table
                            and not norm.get("postcode")
                            and norm.get("country_code")
                            and norm.get("city")
                        ):
                            city_best = lookup_city_best(
                                cities_table=geonames_cities,
                                country_code=norm.get("country_code", ""),
                                city=norm.get("city", ""),
                            ) if geonames_cities else None

                            if city_best and city_best.get("latitude") and city_best.get("longitude"):
                                norm["latitude"] = city_best.get("latitude")
                                norm["longitude"] = city_best.get("longitude")
                                norm["geo_accuracy"] = "city"
                                norm["geonames_match"] = f"{city_best.get('name','')}".strip()

                            pc_hit = lookup_city_to_postcode(
                                postcodes_table=geonames_table,
                                country_code=norm.get("country_code", ""),
                                city=norm.get("city", ""),
                            )
                            if pc_hit and pc_hit.get("postcode"):
                                norm["postcode"] = pc_hit.get("postcode")
                                # if we now have postcode, upgrade match string
                                norm["geonames_match"] = f"{pc_hit.get('place_name','')} {pc_hit.get('postcode','')}".strip()
                                # if lat/lon missing, fill from postcode
                                if not norm.get("latitude") and pc_hit.get("latitude") and pc_hit.get("longitude"):
                                    norm["latitude"] = pc_hit.get("latitude")
                                    norm["longitude"] = pc_hit.get("longitude")
                                    norm["geo_accuracy"] = "postcode"

                        norm.update({
                            "source": "bedrock",
                            "geocode": "geonames_offline",
                            "rendered_prompt": rendered_prompt,
                            "cost": cost,
                        })
                        results[p] = norm
                    except Exception as e:
                        msg = str(e)
                        warnings = ["bedrock_invoke_failed"]
                        if "inference profile" in msg.lower():
                            warnings.append("requires_inference_profile")
                        warnings.append(msg)
                        results[p] = {
                            "source": "bedrock",
                            "geocode": "geonames_offline",
                            "rendered_prompt": rendered_prompt,
                            "warnings": warnings,
                            "confidence": 0.0,
                        }
            elif p == "libpostal_geonames":
                results[p] = {
                    "source": "libpostal",
                    "geocode": "geonames_offline",
                    "warnings": ["pipeline_not_implemented"],
                    "confidence": 0.0,
                }
            elif p == "aws_services":
                place_index = os.getenv("PLACE_INDEX_NAME", "")
                if not place_index:
                    results[p] = {
                        "source": "amazon_location",
                        "geocode": "amazon_location",
                        "warnings": ["missing_place_index"],
                        "confidence": 0.0,
                    }
                else:
                    geo = geocode_with_amazon_location(
                        place_index_name=place_index,
                        text=raw_address,
                        country=country_code,
                        region=os.getenv("AWS_REGION_NAME"),
                    )
                    comp = geo.get("components") or {}
                    per_req = float(pricing.get("location_usd_per_request") or 0)
                    cost = estimate_location_cost_usd(per_request=per_req)
                    results[p] = {
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

        put_submission(
            table_name=table_name,
            user_sub=user_sub,
            submission_id=submission_id,
            created_at=created_at,
            ttl=ttl,
            input_obj={
                "recipient_name": recipient_name,
                "country_code": country_code,
                "raw_address": raw_address,
                "modelId": model_id,
                "pipelines": pipelines,
            },
            results=results,
            preferred_method=None,
        )

        return _resp(200, {
            "submission_id": submission_id,
            "created_at": created_at,
            "user_sub": user_sub,
            "input": {"recipient_name": recipient_name, "country_code": country_code, "raw_address": raw_address, "modelId": model_id},
            "results": results,
            "preferred_method": None,
        })

    return _resp(404, {"error": "not_found"})
