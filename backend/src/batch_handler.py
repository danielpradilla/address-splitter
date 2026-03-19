import json
import os
import urllib.parse
from typing import Any

import boto3

from address_resolver import build_runtime_config_from_env, default_pipelines
from batch_processor import process_batch_csv_text
from prompt_defaults import DEFAULT_PROMPT_TEMPLATE


s3 = boto3.client("s3")


def _parse_pipelines(value: str) -> list[str]:
    items = [part.strip() for part in (value or "").split(",")]
    return [item for item in items if item]


def _output_key(input_key: str, output_prefix: str) -> str:
    base = input_key.rsplit("/", 1)[-1]
    stem = base[:-4] if base.lower().endswith(".csv") else base
    prefix = (output_prefix or "batch-output/").strip("/")
    return f"{prefix}/{stem}.resolved.csv"


def _manifest_key(csv_key: str) -> str:
    return f"{csv_key}.manifest.json"


def _process_one_object(*, bucket: str, key: str) -> dict[str, Any]:
    obj = s3.get_object(Bucket=bucket, Key=key)
    raw = obj["Body"].read().decode("utf-8-sig")

    csv_text, summary = process_batch_csv_text(
        csv_text=raw,
        model_id=os.getenv("BATCH_DEFAULT_MODEL_ID", "").strip(),
        pipelines=_parse_pipelines(os.getenv("BATCH_PIPELINES", "")) or default_pipelines(),
        prompt_template=os.getenv("BATCH_PROMPT_TEMPLATE", "") or DEFAULT_PROMPT_TEMPLATE,
        pricing={},
        runtime_cfg=build_runtime_config_from_env(),
        default_country_code=os.getenv("BATCH_DEFAULT_COUNTRY_CODE", "").strip().upper(),
    )

    output_key = _output_key(key, os.getenv("BATCH_OUTPUT_PREFIX", "batch-output/"))
    s3.put_object(
        Bucket=bucket,
        Key=output_key,
        Body=csv_text.encode("utf-8"),
        ContentType="text/csv; charset=utf-8",
    )

    manifest = {
        "input_bucket": bucket,
        "input_key": key,
        "output_bucket": bucket,
        "output_key": output_key,
        **summary,
    }
    s3.put_object(
        Bucket=bucket,
        Key=_manifest_key(output_key),
        Body=json.dumps(manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    return manifest


def handler(event, context):
    records = event.get("Records") or []
    manifests = []

    if records:
        for record in records:
            s3_info = (record.get("s3") or {})
            bucket = ((s3_info.get("bucket") or {}).get("name") or "").strip()
            key = urllib.parse.unquote_plus(((s3_info.get("object") or {}).get("key") or "").strip())
            if not bucket or not key:
                continue
            manifests.append(_process_one_object(bucket=bucket, key=key))
        return {"processed": manifests}

    bucket = (event.get("bucket") or "").strip()
    key = (event.get("key") or "").strip()
    if not bucket or not key:
        raise ValueError("missing_bucket_or_key")

    manifest = _process_one_object(bucket=bucket, key=key)
    return {"processed": [manifest]}
