import time
from typing import Any

import boto3


def epoch_plus_days(days: int) -> int:
    return int(time.time()) + int(days) * 86400


def submissions_table(name: str):
    return boto3.resource("dynamodb").Table(name)


def user_settings_table(name: str):
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

    table.put_item(Item=item)


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
        KeyConditionExpression=boto3.dynamodb.conditions.Key("GSI1PK").eq(pk),
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
