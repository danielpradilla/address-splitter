#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?Missing AWS_REGION}"
: "${APP_NAME:?Missing APP_NAME}"
: "${STAGE:?Missing STAGE}"

STACK_NAME="${APP_NAME}-${STAGE}"
QUALIFIER="${LIBPOSTAL_ALIAS:-live}"
PC_COUNT="${LIBPOSTAL_PC_COUNT:-1}"

FUNCTION_NAME="$(aws cloudformation describe-stack-resources \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --logical-resource-id ApiFunction \
  --query 'StackResources[0].PhysicalResourceId' \
  --output text)"

echo "Setting provisioned concurrency to ${PC_COUNT} for ${FUNCTION_NAME}:${QUALIFIER}"
aws lambda put-provisioned-concurrency-config \
  --region "$AWS_REGION" \
  --function-name "$FUNCTION_NAME" \
  --qualifier "$QUALIFIER" \
  --provisioned-concurrent-executions "$PC_COUNT" >/dev/null

echo "Waiting for provisioned concurrency to become READY..."
for i in {1..60}; do
  STATUS="$(aws lambda get-provisioned-concurrency-config \
    --region "$AWS_REGION" \
    --function-name "$FUNCTION_NAME" \
    --qualifier "$QUALIFIER" \
    --query 'Status' \
    --output text 2>/dev/null || true)"

  if [[ "$STATUS" == "READY" ]]; then
    echo "READY"
    exit 0
  fi
  if [[ "$STATUS" == "FAILED" ]]; then
    echo "FAILED"
    aws lambda get-provisioned-concurrency-config \
      --region "$AWS_REGION" \
      --function-name "$FUNCTION_NAME" \
      --qualifier "$QUALIFIER" \
      --output json
    exit 1
  fi
  sleep 5
done

if [[ "${STATUS:-}" != "READY" ]]; then
  echo "Timed out waiting for provisioned concurrency readiness."
  exit 1
fi

echo "Running libpostal prewarm call..."
cat > /tmp/libpostal_prewarm_event.json <<'EOF'
{
  "version": "2.0",
  "routeKey": "POST /split",
  "rawPath": "/split",
  "rawQueryString": "",
  "headers": {"content-type":"application/json"},
  "requestContext": {
    "http": {"method": "POST", "path": "/split"},
    "routeKey": "POST /split",
    "authorizer": {"jwt": {"claims": {"sub": "libpostal-warmup"}}}
  },
  "body": "{\"country_code\":\"\",\"raw_address\":\"x\",\"pipelines\":[\"libpostal_geonames\"]}",
  "isBase64Encoded": false
}
EOF

aws lambda invoke \
  --region "$AWS_REGION" \
  --function-name "${FUNCTION_NAME}:${QUALIFIER}" \
  --payload fileb:///tmp/libpostal_prewarm_event.json \
  --cli-read-timeout 420 \
  /tmp/libpostal_prewarm_out.json >/tmp/libpostal_prewarm_meta.json

if grep -q "FunctionError" /tmp/libpostal_prewarm_meta.json; then
  echo "Prewarm invocation returned FunctionError:"
  cat /tmp/libpostal_prewarm_meta.json
  cat /tmp/libpostal_prewarm_out.json
  exit 1
fi

echo "Prewarm complete."
exit 0
