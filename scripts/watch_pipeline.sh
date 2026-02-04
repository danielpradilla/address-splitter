#!/usr/bin/env bash
set -euo pipefail
PROFILE=${AWS_PROFILE:-depr001-deployer}
REGION=${AWS_REGION:-eu-central-1}
PIPELINE=${1:-address-splitter-dev}

while true; do
  status=$(aws codepipeline list-pipeline-executions --pipeline-name "$PIPELINE" --region "$REGION" --profile "$PROFILE" --max-items 1 --query 'pipelineExecutionSummaries[0].status' --output text)
  exec_id=$(aws codepipeline list-pipeline-executions --pipeline-name "$PIPELINE" --region "$REGION" --profile "$PROFILE" --max-items 1 --query 'pipelineExecutionSummaries[0].pipelineExecutionId' --output text)
  echo "[$(date '+%H:%M:%S')] $PIPELINE $exec_id $status"

  if [ "$status" = "Succeeded" ]; then
    exit 0
  fi
  if [ "$status" = "Failed" ]; then
    exit 2
  fi
  sleep 15

done
