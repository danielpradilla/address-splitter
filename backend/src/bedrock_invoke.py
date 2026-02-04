import json
import os
from typing import Any

import boto3


def invoke_bedrock_json(*, model_id: str, prompt: str, region: str | None = None) -> dict[str, Any]:
    """Invoke a Bedrock text/chat model and return parsed JSON.

    Implementation: best-effort for common providers using bedrock-runtime.
    """
    brt = boto3.client("bedrock-runtime", region_name=region)

    # Heuristic by provider prefix
    if model_id.startswith("anthropic."):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 800,
            "temperature": 0,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]},
            ],
        }
        resp = brt.invoke_model(modelId=model_id, body=json.dumps(body))
        raw = resp["body"].read().decode("utf-8")
        data = json.loads(raw)
        # Claude returns content as list
        text = ""
        if isinstance(data.get("content"), list) and data["content"]:
            text = data["content"][0].get("text") or ""
        elif isinstance(data.get("completion"), str):
            text = data["completion"]
        else:
            text = raw
        return json.loads(_extract_json(text))

    # Fallback: treat as text model with prompt field
    body = {"prompt": prompt, "max_tokens": 800, "temperature": 0}
    resp = brt.invoke_model(modelId=model_id, body=json.dumps(body))
    raw = resp["body"].read().decode("utf-8")
    try:
        data = json.loads(raw)
        # try common shapes
        text = data.get("completion") or data.get("output") or data.get("generation") or raw
    except Exception:
        text = raw

    return json.loads(_extract_json(text))


def _extract_json(text: str) -> str:
    """Extract first JSON object substring from model output."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]

    raise ValueError("model_output_not_json")
