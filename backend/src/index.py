import os
import time

from http_utils import cors_headers, response
from routes_models import handle_get_models
from routes_prompt import handle_get_prompt, handle_put_prompt
from routes_split import handle_post_split
from routes_submissions import (
    handle_get_batch_job,
    handle_get_recent,
    handle_get_submission,
    handle_list_batch_jobs,
    handle_put_preferred,
)


def _get_user_sub(event: dict) -> str:
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
        return {"statusCode": 204, "headers": cors_headers(), "body": ""}

    if route_key == "GET /health":
        return response(200, {"ok": True, "ts": int(time.time())})

    try:
        user_sub = _get_user_sub(event)
    except Exception:
        return response(401, {"error": "unauthorized"})

    if route_key == "GET /prompt":
        return handle_get_prompt(table_name=os.getenv("USER_SETTINGS_TABLE", ""), user_sub=user_sub)
    if route_key == "PUT /prompt":
        return handle_put_prompt(event=event, table_name=os.getenv("USER_SETTINGS_TABLE", ""), user_sub=user_sub)
    if route_key == "GET /models":
        return handle_get_models()
    if route_key == "GET /recent":
        return handle_get_recent(user_sub=user_sub)
    if route_key == "GET /submission/{id}":
        return handle_get_submission(event=event, user_sub=user_sub)
    if route_key == "PUT /submission/{id}/preferred":
        return handle_put_preferred(event=event, user_sub=user_sub)
    if route_key == "POST /split":
        return handle_post_split(event=event, user_sub=user_sub)
    if route_key == "GET /batch-jobs":
        return handle_list_batch_jobs(event=event, user_sub=user_sub)
    if route_key == "GET /batch-jobs/{id}":
        return handle_get_batch_job(event=event, user_sub=user_sub)

    return response(404, {"error": "not_found"})
