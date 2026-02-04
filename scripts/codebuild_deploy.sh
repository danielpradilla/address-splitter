#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?Missing AWS_REGION}"
: "${STACK_NAME:?Missing STACK_NAME}"
: "${STAGE:?Missing STAGE}"
: "${ALLOWED_ORIGINS:=*}"

echo "Packaging Lambda"
ARTIFACT_BUCKET=$(aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE-pipeline" \
  --query "Stacks[0].Outputs[?OutputKey=='ArtifactBucketName'].OutputValue" \
  --output text)

LAMBDA_ZIP="/tmp/${STACK_NAME}-${STAGE}-api.zip"
rm -f "$LAMBDA_ZIP"
(cd backend/src && zip -r "$LAMBDA_ZIP" . -x "__pycache__/*" "*.pyc")

SRC_VER=${CODEBUILD_RESOLVED_SOURCE_VERSION:-$(date +%s)}
LAMBDA_KEY="lambda/${STACK_NAME}-${STAGE}-api-${SRC_VER}.zip"
aws s3 cp "$LAMBDA_ZIP" "s3://$ARTIFACT_BUCKET/$LAMBDA_KEY"

echo "Deploying CloudFormation stack"
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE" \
  --template-file infra/cloudformation/main.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
      AllowedOrigins="$ALLOWED_ORIGINS" \
      LambdaCodeS3Bucket="$ARTIFACT_BUCKET" \
      LambdaCodeS3Key="$LAMBDA_KEY"

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

echo "Generating frontend/config.js"
API_BASE_URL=$(aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiBaseUrl'].OutputValue" \
  --output text)
COGNITO_DOMAIN=$(aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE" \
  --query "Stacks[0].Outputs[?OutputKey=='CognitoDomain'].OutputValue" \
  --output text)
COGNITO_APP_CLIENT_ID=$(aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE" \
  --query "Stacks[0].Outputs[?OutputKey=='CognitoAppClientId'].OutputValue" \
  --output text)
CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
  --output text)

DEPLOY_ID=${CODEBUILD_RESOLVED_SOURCE_VERSION:-unknown}
DEPLOY_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > frontend/config.js <<EOF
window.__CONFIG__ = {
  apiBaseUrl: "${API_BASE_URL}",
  cognitoDomain: "${COGNITO_DOMAIN}",
  cognitoClientId: "${COGNITO_APP_CLIENT_ID}",
  redirectUri: "${CLOUDFRONT_URL}",
  deployId: "${DEPLOY_ID}",
  deployTime: "${DEPLOY_TIME}",
};
EOF

echo "Syncing frontend to S3 bucket: $FRONTEND_BUCKET"
aws s3 sync frontend/ "s3://$FRONTEND_BUCKET/" --delete

echo "Invalidating CloudFront distribution: $DISTRIBUTION_ID"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*"
