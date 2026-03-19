import json
import os
import time
from typing import Any, Dict

import boto3

from address_resolver import allowed_pipelines, build_runtime_config_from_env, default_pipelines, resolve_address
from models import list_bedrock_models
from prompting import render_prompt, validate_template
from prompt_defaults import DEFAULT_PROMPT_TEMPLATE
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
        def _sanitize_prompt(tpl: str) -> str:
            # Backward-compat: strip deprecated {name} placeholder and any related lines.
            if not tpl:
                return tpl
            tpl2 = tpl
            tpl2 = tpl2.replace("- Recipient name: {name}\n", "")
            tpl2 = tpl2.replace("Recipient name: {name}\n", "")
            tpl2 = tpl2.replace("{name}", "")
            return tpl2

        if item and item.get("prompt_template"):
            tpl = item["prompt_template"]
            tpl2 = _sanitize_prompt(tpl)
            if tpl2 != tpl:
                table.update_item(
                    Key={"user_sub": user_sub},
                    UpdateExpression="SET prompt_template = :t",
                    ExpressionAttributeValues={":t": tpl2},
                )
                tpl = tpl2

            return _resp(
                200,
                {
                    "prompt_template": tpl,
                    "is_default": False,
                    "pricing": item.get("pricing") or {},
                },
            )

        # Default demo prompt
        demo = DEFAULT_PROMPT_TEMPLATE
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
        # Backward-compat: auto-strip deprecated placeholder
        prompt = prompt.replace("{name}", "")
        prompt = prompt.replace("- Recipient name: {name}\n", "")
        prompt = prompt.replace("Recipient name: {name}\n", "")
        try:
            validate_template(prompt)
        except Exception as e:
            return _resp(400, {"error": "invalid_prompt", "message": str(e)})

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
                        "state_region": r.get("state_region", ""),
                        "country_code": r.get("country_code", ""),
                        "geocode": r.get("geocode", ""),
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
                        "model_id": inp.get("modelId", ""),
                        "raw_address_preview": (inp.get("raw_address") or "").replace("\n", ", ")[:120],
                        "preferred_method": it.get("preferred_method"),
                        "pipelines": {
                            "bedrock_geonames": _summ(res.get("bedrock_geonames")),
                            "libpostal_geonames": _summ(res.get("libpostal_geonames")),
                            "aws_services": _summ(res.get("aws_services")),
                            "loqate": _summ(res.get("loqate")),
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
        allowed = allowed_pipelines()
        if preferred not in allowed:
            return _resp(400, {"error": "invalid_preferred_method", "allowed": sorted(list(allowed))})

        set_preferred(table_name=table_name, user_sub=user_sub, submission_id=submission_id, preferred_method=preferred)
        return _resp(200, {"ok": True})

    if route_key == "POST /split":
        table_name = os.getenv("SUBMISSIONS_TABLE", "")
        settings_table_name = os.getenv("USER_SETTINGS_TABLE", "")
        if not table_name or not settings_table_name:
            return _resp(500, {"error": "missing_config"})

        body = event.get("body") or "{}"
        try:
            data = json.loads(body)
        except Exception:
            return _resp(400, {"error": "invalid_json"})

        country_code = (data.get("country_code") or "").strip().upper()
        raw_address = (data.get("raw_address") or "").strip()
        model_id = (data.get("modelId") or "").strip()
        pipelines = data.get("pipelines") or default_pipelines()

        if not raw_address:
            return _resp(400, {"error": "missing_fields", "required": ["raw_address"], "optional": ["country_code"]})

        if not country_code:
            # v1 behavior: allow empty country (auto-detect to be implemented in pipeline #1 later).
            country_code = ""

        # prompt render (for future use)
        prompt_t = user_settings_table(settings_table_name).get_item(Key={"user_sub": user_sub}).get("Item", {}).get("prompt_template")
        if not prompt_t:
            prompt_t = DEFAULT_PROMPT_TEMPLATE
        try:
            validate_template(prompt_t)
        except Exception as e:
            return _resp(400, {"error": "invalid_prompt", "message": str(e)})
        rendered_prompt = render_prompt(prompt_t, country=country_code, address=raw_address)

        # Pricing settings (optional)
        pricing = user_settings_table(settings_table_name).get_item(Key={"user_sub": user_sub}).get("Item", {}).get("pricing") or {}

        submission_id = new_ulid()
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ttl = epoch_plus_days(int(os.getenv("RESULTS_RETENTION_DAYS", "30")))

        runtime_cfg = build_runtime_config_from_env()
        results = resolve_address(
            country_code=country_code,
            raw_address=raw_address,
            model_id=model_id,
            pipelines=pipelines,
            rendered_prompt=rendered_prompt,
            pricing=pricing,
            **runtime_cfg,
        )

        t_put = time.perf_counter()
        put_submission(
            table_name=table_name,
            user_sub=user_sub,
            submission_id=submission_id,
            created_at=created_at,
            ttl=ttl,
            input_obj={
                "country_code": country_code,
                "raw_address": raw_address,
                "modelId": model_id,
                "pipelines": pipelines,
            },
            results=results,
            preferred_method=None,
        )
        print(
            f"[timing] route=POST /split step=put_submission ms={(time.perf_counter() - t_put) * 1000:.1f}",
            flush=True,
        )

        return _resp(200, {
            "submission_id": submission_id,
            "created_at": created_at,
            "user_sub": user_sub,
            "input": {"country_code": country_code, "raw_address": raw_address, "modelId": model_id},
            "results": results,
            "preferred_method": None,
        })

    return _resp(404, {"error": "not_found"})
