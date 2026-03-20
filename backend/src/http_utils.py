import json
import os
from typing import Any


def cors_headers() -> dict[str, str]:
    origin = os.getenv("ALLOWED_ORIGINS", "*")
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "authorization,content-type",
        "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
    }


def response(status: int, body: Any):
    return {"statusCode": status, "headers": cors_headers(), "body": json.dumps(body)}


def parse_json_body(event: dict) -> tuple[dict[str, Any] | None, dict | None]:
    body = event.get("body") or "{}"
    try:
        return json.loads(body), None
    except Exception:
        return None, response(400, {"error": "invalid_json"})
