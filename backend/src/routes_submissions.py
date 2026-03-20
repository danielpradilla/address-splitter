import os

from address_resolver import allowed_pipelines
from http_utils import parse_json_body, response
from storage import get_batch_job, get_submission, list_batch_jobs, list_recent, set_preferred


def handle_get_recent(*, user_sub: str):
    table_name = os.getenv("SUBMISSIONS_TABLE", "")
    if not table_name:
        return response(500, {"error": "missing_config", "field": "SUBMISSIONS_TABLE"})
    try:
        items = list_recent(table_name=table_name, user_sub=user_sub, limit=10)
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
        return response(200, {"items": out})
    except Exception as e:
        return response(500, {"error": "recent_failed", "message": str(e)})


def handle_get_submission(*, event: dict, user_sub: str):
    table_name = os.getenv("SUBMISSIONS_TABLE", "")
    if not table_name:
        return response(500, {"error": "missing_config", "field": "SUBMISSIONS_TABLE"})
    submission_id = (event.get("pathParameters") or {}).get("id")
    if not submission_id:
        return response(400, {"error": "missing_id"})
    item = get_submission(table_name=table_name, user_sub=user_sub, submission_id=submission_id)
    if not item:
        return response(404, {"error": "not_found"})
    return response(200, item)


def handle_put_preferred(*, event: dict, user_sub: str):
    table_name = os.getenv("SUBMISSIONS_TABLE", "")
    if not table_name:
        return response(500, {"error": "missing_config", "field": "SUBMISSIONS_TABLE"})
    submission_id = (event.get("pathParameters") or {}).get("id")
    if not submission_id:
        return response(400, {"error": "missing_id"})
    data, error = parse_json_body(event)
    if error:
        return error
    preferred = (data.get("preferred_method") or "").strip()
    allowed = allowed_pipelines()
    if preferred not in allowed:
        return response(400, {"error": "invalid_preferred_method", "allowed": sorted(list(allowed))})
    set_preferred(table_name=table_name, user_sub=user_sub, submission_id=submission_id, preferred_method=preferred)
    return response(200, {"ok": True})


def handle_list_batch_jobs(*, event: dict, user_sub: str):
    table_name = os.getenv("BATCH_JOBS_TABLE", "")
    if not table_name:
        return response(500, {"error": "missing_config", "field": "BATCH_JOBS_TABLE"})
    params = event.get("queryStringParameters") or {}
    try:
        limit = int(params.get("limit") or 20)
    except Exception:
        limit = 20
    limit = max(1, min(limit, 50))
    return response(200, {"items": list_batch_jobs(table_name=table_name, user_sub=user_sub, limit=limit)})


def handle_get_batch_job(*, event: dict, user_sub: str):
    table_name = os.getenv("BATCH_JOBS_TABLE", "")
    if not table_name:
        return response(500, {"error": "missing_config", "field": "BATCH_JOBS_TABLE"})
    job_id = (event.get("pathParameters") or {}).get("id")
    if not job_id:
        return response(400, {"error": "missing_id"})
    item = get_batch_job(table_name=table_name, job_id=job_id)
    if not item or item.get("user_sub") != user_sub:
        return response(404, {"error": "not_found"})
    return response(200, item)
