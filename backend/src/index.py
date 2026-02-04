import json
import os
import time
from typing import Any, Dict

import boto3

from aws_location import geocode_with_amazon_location
from models import list_bedrock_models
from prompting import render_prompt, validate_template
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
            return _resp(200, {"prompt_template": item["prompt_template"], "is_default": False})

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
        return _resp(200, {"prompt_template": demo, "is_default": True})

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
        table.put_item(
            Item={
                "user_sub": user_sub,
                "prompt_template": prompt,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        return _resp(200, {"ok": True})

    if route_key == "GET /models":
        try:
            models = list_bedrock_models(region=os.getenv("AWS_REGION_NAME"))
            return _resp(200, {"models": models})
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

        if not recipient_name or not country_code or not raw_address:
            return _resp(400, {"error": "missing_fields", "required": ["recipient_name","country_code","raw_address"]})

        # prompt render (for future use)
        prompt_t = user_settings_table(settings_table_name).get_item(Key={"user_sub": user_sub}).get("Item", {}).get("prompt_template")
        if not prompt_t:
            prompt_t = "Take the {country} and split the following address: {address}. Return ONLY JSON."
        try:
            validate_template(prompt_t)
        except Exception as e:
            return _resp(400, {"error": "invalid_prompt", "message": str(e)})
        rendered_prompt = render_prompt(prompt_t, name=recipient_name, country=country_code, address=raw_address)

        submission_id = new_ulid()
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ttl = epoch_plus_days(int(os.getenv("RESULTS_RETENTION_DAYS", "30")))

        results = {}
        for p in pipelines:
            if p == "bedrock_geonames":
                results[p] = {
                    "source": "bedrock",
                    "geocode": "geonames_offline",
                    "rendered_prompt": rendered_prompt,
                    "warnings": ["pipeline_not_implemented"],
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
