import json
import os
import time
from typing import Any, Dict

import boto3

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

        # Default demo prompt (kept simple here; can be replaced later)
        demo = "Take the {country} and split the following address: {address}. Return ONLY JSON."
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
            # Return a thin preview list
            out = []
            for it in items:
                inp = it.get("input") or {}
                out.append(
                    {
                        "submission_id": it.get("submission_id"),
                        "created_at": it.get("created_at"),
                        "country_code": inp.get("country_code"),
                        "recipient_name": inp.get("recipient_name"),
                        "raw_address_preview": (inp.get("raw_address") or "").replace("\n", ", ")[:120],
                        "preferred_method": it.get("preferred_method"),
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
                results[p] = {"source": "bedrock", "geocode": "geonames_offline", "rendered_prompt": rendered_prompt, "warnings": ["pipeline_not_implemented"], "confidence": 0.0}
            elif p == "libpostal_geonames":
                results[p] = {"source": "libpostal", "geocode": "geonames_offline", "warnings": ["pipeline_not_implemented"], "confidence": 0.0}
            elif p == "aws_services":
                results[p] = {"source": "amazon_location", "geocode": "amazon_location", "warnings": ["pipeline_not_implemented"], "confidence": 0.0}

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
