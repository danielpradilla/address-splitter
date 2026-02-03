#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?Missing AWS_REGION}"
: "${APP_NAME:?Missing APP_NAME}"
: "${STAGE:?Missing STAGE}"
: "${GITHUB_REPO:?Missing GITHUB_REPO}"
: "${GITHUB_BRANCH:?Missing GITHUB_BRANCH}"
: "${CODESTAR_ARN:?Missing CODESTAR_ARN}"

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$APP_NAME-$STAGE-pipeline" \
  --template-file infra/cloudformation/pipeline.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      AppName="$APP_NAME" \
      Stage="$STAGE" \
      AwsRegion="$AWS_REGION" \
      GitHubRepo="$GITHUB_REPO" \
      GitHubBranch="$GITHUB_BRANCH" \
      CodeStarConnectionArn="$CODESTAR_ARN"
