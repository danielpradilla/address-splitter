import time
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key


def epoch_plus_days(days: int) -> int:
    return int(time.time()) + int(days) * 86400


def _clean_for_ddb(value: Any):
    # DynamoDB via boto3 does not accept float; use int or string.
    # For our use-case, latitude/longitude can be stored as strings.
    if isinstance(value, float):
        # Store as string to satisfy boto3 DDB type constraints (no floats), but keep precision.
        return format(value, ".12f")
    if isinstance(value, dict):
        return {k: _clean_for_ddb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_for_ddb(v) for v in value]
    return value


def submissions_table(name: str):
    return boto3.resource("dynamodb").Table(name)


def user_settings_table(name: str):
    return boto3.resource("dynamodb").Table(name)


def batch_jobs_table(name: str):
    return boto3.resource("dynamodb").Table(name)


def put_submission(
    *,
    table_name: str,
    user_sub: str,
    submission_id: str,
    created_at: str,
    ttl: int,
    input_obj: dict,
    results: dict,
    preferred_method: str | None,
):
    table = submissions_table(table_name)

    pk = f"USER#{user_sub}"
    sk = f"SUB#{submission_id}"

    item: dict[str, Any] = {
        "PK": pk,
        "SK": sk,
        "submission_id": submission_id,
        "created_at": created_at,
        "user_sub": user_sub,
        "ttl": ttl,
        "input": input_obj,
        "results": results,
        "preferred_method": preferred_method,
        "GSI1PK": pk,
        "GSI1SK": f"TS#{created_at}#SUB#{submission_id}",
    }

    table.put_item(Item=_clean_for_ddb(item))


def get_submission(*, table_name: str, user_sub: str, submission_id: str) -> dict | None:
    table = submissions_table(table_name)
    pk = f"USER#{user_sub}"
    sk = f"SUB#{submission_id}"
    resp = table.get_item(Key={"PK": pk, "SK": sk})
    return resp.get("Item")


def list_recent(*, table_name: str, user_sub: str, limit: int = 10) -> list[dict]:
    table = submissions_table(table_name)
    pk = f"USER#{user_sub}"
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(pk),
        ScanIndexForward=False,
        Limit=limit,
    )
    return resp.get("Items") or []


def set_preferred(*, table_name: str, user_sub: str, submission_id: str, preferred_method: str):
    table = submissions_table(table_name)
    pk = f"USER#{user_sub}"
    sk = f"SUB#{submission_id}"
    table.update_item(
        Key={"PK": pk, "SK": sk},
        UpdateExpression="SET preferred_method = :p",
        ExpressionAttributeValues={":p": preferred_method},
    )


def create_batch_job(
    *,
    table_name: str,
    job_id: str,
    user_sub: str,
    created_at: str,
    ttl: int,
    input_bucket: str,
    input_key: str,
    config: dict | None = None,
    status: str = "RECEIVED",
):
    table = batch_jobs_table(table_name)
    item: dict[str, Any] = {
        "PK": f"JOB#{job_id}",
        "SK": "META",
        "job_id": job_id,
        "user_sub": user_sub,
        "created_at": created_at,
        "updated_at": created_at,
        "ttl": ttl,
        "status": status,
        "input_bucket": input_bucket,
        "input_key": input_key,
        "config": config or {},
        "GSI1PK": f"USER#{user_sub}",
        "GSI1SK": f"TS#{created_at}#JOB#{job_id}",
    }
    table.put_item(Item=_clean_for_ddb(item))
    return item


def update_batch_job(
    *,
    table_name: str,
    job_id: str,
    updates: dict[str, Any],
):
    table = batch_jobs_table(table_name)
    parts = []
    expr_values: dict[str, Any] = {}
    expr_names: dict[str, str] = {}
    for idx, (key, value) in enumerate(updates.items(), start=1):
        name_key = f"#n{idx}"
        value_key = f":v{idx}"
        expr_names[name_key] = key
        expr_values[value_key] = _clean_for_ddb(value)
        parts.append(f"{name_key} = {value_key}")

    table.update_item(
        Key={"PK": f"JOB#{job_id}", "SK": "META"},
        UpdateExpression="SET " + ", ".join(parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def get_batch_job(*, table_name: str, job_id: str) -> dict | None:
    table = batch_jobs_table(table_name)
    resp = table.get_item(Key={"PK": f"JOB#{job_id}", "SK": "META"})
    return resp.get("Item")


def list_batch_jobs(*, table_name: str, user_sub: str, limit: int = 20) -> list[dict]:
    table = batch_jobs_table(table_name)
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_sub}"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return resp.get("Items") or []
