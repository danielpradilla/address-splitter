#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?Missing AWS_REGION}"
: "${APP_NAME:?Missing APP_NAME}"
: "${STAGE:?Missing STAGE}"

STACK_NAME="${APP_NAME}-${STAGE}"
QUALIFIER="${LIBPOSTAL_ALIAS:-live}"

FUNCTION_NAME="$(aws cloudformation describe-stack-resources \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --logical-resource-id ApiFunction \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)"

echo "Removing provisioned concurrency for ${FUNCTION_NAME}:${QUALIFIER}"
aws lambda delete-provisioned-concurrency-config \
  --region "$AWS_REGION" \
  --function-name "$FUNCTION_NAME" \
  --qualifier "$QUALIFIER" >/dev/null || true

echo "SLEEP"
