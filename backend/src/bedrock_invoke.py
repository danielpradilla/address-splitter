import json
import os
from typing import Any

import boto3


def invoke_bedrock_json(*, model_id: str, prompt: str, region: str | None = None) -> dict[str, Any]:
    """Invoke a Bedrock model and return parsed JSON.

    Strategy:
    1) Prefer the Bedrock Runtime **Converse** API when available (works across many vendors).
    2) Fallback to InvokeModel with Anthropic messages format for Claude.

    Note: model_id can be a foundation model id or an inference profile ARN.
    """
    brt = boto3.client("bedrock-runtime", region_name=region)

    # 1) Converse (best cross-vendor path)
    try:
        resp = brt.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 800, "temperature": 0.0},
        )
        out = (((resp.get("output") or {}).get("message") or {}).get("content") or [])
        text = out[0].get("text") if out else None
        if not text:
            raise ValueError("empty_converse_response")
        return json.loads(_extract_json(text))
    except Exception:
        pass

    # 2) InvokeModel Anthropic Claude messages format
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
        text = ""
        if isinstance(data.get("content"), list) and data["content"]:
            text = data["content"][0].get("text") or ""
        elif isinstance(data.get("completion"), str):
            text = data["completion"]
        else:
            text = raw
        return json.loads(_extract_json(text))

    raise ValueError("no_supported_adapter_for_model")


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
