import os
import time

from address_resolver import build_runtime_config_from_env, default_pipelines, resolve_address
from http_utils import parse_json_body, response
from prompting import render_prompt
from settings_service import get_effective_settings
from storage import epoch_plus_days, put_submission
from ulid_util import new_ulid


def handle_post_split(*, event: dict, user_sub: str):
    table_name = os.getenv("SUBMISSIONS_TABLE", "")
    settings_table_name = os.getenv("USER_SETTINGS_TABLE", "")
    if not table_name or not settings_table_name:
        return response(500, {"error": "missing_config"})

    data, error = parse_json_body(event)
    if error:
        return error

    country_code = (data.get("country_code") or "").strip().upper()
    raw_address = (data.get("raw_address") or "").strip()
    model_id = (data.get("modelId") or "").strip()
    pipelines = data.get("pipelines") or default_pipelines()

    if not raw_address:
        return response(400, {"error": "missing_fields", "required": ["raw_address"], "optional": ["country_code"]})

    settings = get_effective_settings(table_name=settings_table_name, user_sub=user_sub)
    rendered_prompt = render_prompt(
        settings["prompt_template"],
        country=country_code,
        address=raw_address,
    )

    submission_id = new_ulid()
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ttl = epoch_plus_days(int(os.getenv("RESULTS_RETENTION_DAYS", "30")))
    results = resolve_address(
        country_code=country_code,
        raw_address=raw_address,
        model_id=model_id,
        pipelines=pipelines,
        rendered_prompt=rendered_prompt,
        pricing=settings["pricing"],
        **build_runtime_config_from_env(),
    )

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

    return response(
        200,
        {
            "submission_id": submission_id,
            "created_at": created_at,
            "user_sub": user_sub,
            "input": {"country_code": country_code, "raw_address": raw_address, "modelId": model_id},
            "results": results,
            "preferred_method": None,
        },
    )
