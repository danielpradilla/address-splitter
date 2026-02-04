#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?Missing AWS_REGION}"
: "${STACK_NAME:?Missing STACK_NAME}"
: "${STAGE:?Missing STAGE}"
: "${ALLOWED_ORIGINS:=*}"

echo "Building + pushing Lambda container image (libpostal + Senzing model)"
SRC_VER=${CODEBUILD_RESOLVED_SOURCE_VERSION:-$(date +%s)}

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO_NAME="${STACK_NAME}-${STAGE}-api"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"
IMAGE_TAG="${SRC_VER}"
IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"

aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$REPO_NAME" >/dev/null 2>&1 || \
  aws ecr create-repository --region "$AWS_REGION" --repository-name "$REPO_NAME" >/dev/null

aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Build from repo root so Dockerfile can COPY backend/...
docker build -t "$IMAGE_URI" -f backend/Dockerfile .
docker push "$IMAGE_URI"

echo "Deploying CloudFormation stack"
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME-$STAGE" \
  --template-file infra/cloudformation/main.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
      AllowedOrigins="$ALLOWED_ORIGINS" \
      LambdaImageUri="$IMAGE_URI"

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
# Upload everything except config.js
aws s3 sync frontend/ "s3://$FRONTEND_BUCKET/" --delete --exclude "config.js"

# Upload config.js with no-cache headers so deployId updates are visible immediately
aws s3 cp frontend/config.js "s3://$FRONTEND_BUCKET/config.js" \
  --cache-control "no-store, no-cache, must-revalidate, max-age=0" \
  --content-type "application/javascript"

echo "Invalidating CloudFront distribution: $DISTRIBUTION_ID"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*"
