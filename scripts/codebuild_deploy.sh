#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?Missing AWS_REGION}"
: "${STACK_NAME:?Missing STACK_NAME}"
: "${STAGE:?Missing STAGE}"

echo "Deploying CloudFormation stack"
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE" \
  --template-file infra/cloudformation/main.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

echo "Fetching outputs"
FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE" \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
  --output text)
export FRONTEND_BUCKET

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
  --output text)
export DISTRIBUTION_ID

echo "Syncing frontend to S3 bucket: $FRONTEND_BUCKET"
aws s3 sync frontend/ "s3://$FRONTEND_BUCKET/" --delete

echo "Invalidating CloudFront distribution: $DISTRIBUTION_ID"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*"
