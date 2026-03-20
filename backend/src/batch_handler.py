import json
import os
import time
import urllib.parse
from typing import Any

import boto3

from address_resolver import build_runtime_config_from_env, default_pipelines
from batch_processor import process_batch_csv_text
from settings_service import get_batch_settings_from_env
from storage import create_batch_job, epoch_plus_days, update_batch_job
from ulid_util import new_ulid


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
    metadata = obj.get("Metadata") or {}
    job_id = (metadata.get("job-id") or "").strip() or new_ulid()
    user_sub = (metadata.get("user-sub") or "").strip() or "system"
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    jobs_table_name = os.getenv("BATCH_JOBS_TABLE", "")
    settings = get_batch_settings_from_env()

    if jobs_table_name:
        create_batch_job(
            table_name=jobs_table_name,
            job_id=job_id,
            user_sub=user_sub,
            created_at=created_at,
            ttl=epoch_plus_days(int(os.getenv("RESULTS_RETENTION_DAYS", "30"))),
            input_bucket=bucket,
            input_key=key,
            config={
                "pipelines": _parse_pipelines(os.getenv("BATCH_PIPELINES", "")) or default_pipelines(),
                "default_country_code": os.getenv("BATCH_DEFAULT_COUNTRY_CODE", "").strip().upper(),
            },
            status="PROCESSING",
        )

    try:
        csv_text, summary = process_batch_csv_text(
            csv_text=raw,
            model_id=os.getenv("BATCH_DEFAULT_MODEL_ID", "").strip(),
            pipelines=_parse_pipelines(os.getenv("BATCH_PIPELINES", "")) or default_pipelines(),
            prompt_template=settings["prompt_template"],
            pricing=settings["pricing"],
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
            "job_id": job_id,
            "user_sub": user_sub,
            "input_bucket": bucket,
            "input_key": key,
            "output_bucket": bucket,
            "output_key": output_key,
            "status": "SUCCEEDED",
            **summary,
        }
        s3.put_object(
            Bucket=bucket,
            Key=_manifest_key(output_key),
            Body=json.dumps(manifest, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        if jobs_table_name:
            update_batch_job(
                table_name=jobs_table_name,
                job_id=job_id,
                updates={
                    "status": "SUCCEEDED",
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "output_bucket": bucket,
                    "output_key": output_key,
                    "rows_processed": summary["rows_processed"],
                    "rows_failed": summary["rows_failed"],
                },
            )
        return manifest
    except Exception as exc:
        if jobs_table_name:
            update_batch_job(
                table_name=jobs_table_name,
                job_id=job_id,
                updates={
                    "status": "FAILED",
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "error": str(exc),
                },
            )
        raise


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
