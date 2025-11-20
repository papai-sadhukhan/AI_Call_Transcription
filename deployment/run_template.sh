#!/bin/bash

# Run Dataflow job using Flex Template
# Usage: ./deployment/run_template.sh [dev|prod]

set -e

ENVIRONMENT=${1:-dev}

if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "Usage: $0 [dev|prod]"
    exit 1
fi

PROJECT_ID="skyuk-uk-reg-expmnt-dev"
REGION="europe-west1"
TEMPLATE_SPEC="gs://dataflow-staging-europe-west1-181982885154/templates/pii-redaction-flex-template.json"
JOB_NAME="call-transcript-redaction-$(date +%Y%m%d-%H%M%S)"

if [ "$ENVIRONMENT" == "dev" ]; then
    CONFIG_FILE="config/config_dev.json"
    echo "========================================="
    echo "Launching DEV Dataflow Job"
    echo "========================================="
else
    CONFIG_FILE="config/config_prod.json"
    echo "========================================="
    echo "Launching PROD Dataflow Job"
    echo "========================================="
fi

echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Config: $CONFIG_FILE"
echo "Job Name: $JOB_NAME"
echo "Template: $TEMPLATE_SPEC"
echo "========================================="

# Launch Dataflow job from Flex Template
gcloud dataflow flex-template run "$JOB_NAME" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --template-file-gcs-location="$TEMPLATE_SPEC" \
    --parameters config_path="$CONFIG_FILE" \
    --parameters runner="DataflowRunner" \
    --parameters log_level="INFO"

echo ""
echo "========================================="
echo "Job launched successfully!"
echo "========================================="
echo "Job Name: $JOB_NAME"
echo "Monitor: https://console.cloud.google.com/dataflow/jobs/$REGION/$JOB_NAME?project=$PROJECT_ID"
echo "========================================="
