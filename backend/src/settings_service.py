import os
import time
from typing import Any

from prompt_defaults import DEFAULT_PROMPT_TEMPLATE
from prompting import validate_template
from storage import user_settings_table


DEFAULT_PRICING = {
    "bedrock_input_usd_per_million": 3.0,
    "bedrock_output_usd_per_million": 15.0,
    "location_usd_per_request": 0.005,
}


def sanitize_prompt_template(template: str) -> str:
    if not template:
        return template
    out = template
    out = out.replace("- Recipient name: {name}\n", "")
    out = out.replace("Recipient name: {name}\n", "")
    out = out.replace("{name}", "")
    return out


def load_user_settings(*, table_name: str, user_sub: str | None) -> dict[str, Any]:
    if not table_name or not user_sub:
        return {}
    item = user_settings_table(table_name).get_item(Key={"user_sub": user_sub}).get("Item")
    return item or {}


def get_effective_settings(*, table_name: str, user_sub: str | None) -> dict[str, Any]:
    item = load_user_settings(table_name=table_name, user_sub=user_sub)
    prompt_template = sanitize_prompt_template(item.get("prompt_template") or DEFAULT_PROMPT_TEMPLATE)
    pricing = dict(DEFAULT_PRICING)
    if isinstance(item.get("pricing"), dict):
        pricing.update(item["pricing"])
    return {
        "prompt_template": prompt_template,
        "pricing": pricing,
        "is_default": not bool(item.get("prompt_template")),
    }


def save_user_settings(
    *,
    table_name: str,
    user_sub: str,
    prompt_template: str,
    pricing: dict[str, Any] | None,
) -> dict[str, Any]:
    prompt = sanitize_prompt_template((prompt_template or "").strip())
    validate_template(prompt)
    item = {
        "user_sub": user_sub,
        "prompt_template": prompt,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if isinstance(pricing, dict):
        item["pricing"] = pricing
    user_settings_table(table_name).put_item(Item=item)
    return item


def get_batch_settings_from_env() -> dict[str, Any]:
    prompt = sanitize_prompt_template(os.getenv("BATCH_PROMPT_TEMPLATE", "") or DEFAULT_PROMPT_TEMPLATE)
    validate_template(prompt)
    return {
        "prompt_template": prompt,
        "pricing": dict(DEFAULT_PRICING),
        "is_default": True,
    }
