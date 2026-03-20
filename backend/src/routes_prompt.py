from http_utils import parse_json_body, response
from settings_service import get_effective_settings, save_user_settings


def handle_get_prompt(*, table_name: str, user_sub: str):
    if not table_name:
        return response(500, {"error": "missing_config", "field": "USER_SETTINGS_TABLE"})
    return response(200, get_effective_settings(table_name=table_name, user_sub=user_sub))


def handle_put_prompt(*, event: dict, table_name: str, user_sub: str):
    if not table_name:
        return response(500, {"error": "missing_config", "field": "USER_SETTINGS_TABLE"})
    data, error = parse_json_body(event)
    if error:
        return error
    try:
        save_user_settings(
            table_name=table_name,
            user_sub=user_sub,
            prompt_template=(data.get("prompt_template") or ""),
            pricing=data.get("pricing"),
        )
        return response(200, {"ok": True})
    except Exception as e:
        return response(400, {"error": "invalid_prompt", "message": str(e)})
