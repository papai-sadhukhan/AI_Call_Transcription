#!/bin/bash

# Run Dataflow Flex Template Job
# Usage: ./run_template.sh [dev|prod]

set -e

# Determine environment
ENV=${1:-dev}

if [ "$ENV" != "dev" ] && [ "$ENV" != "prod" ]; then
    echo "Usage: ./run_template.sh [dev|prod]"
    exit 1
fi

# Configuration based on environment
if [ "$ENV" = "dev" ]; then
    PROJECT_ID="skyuk-uk-reg-expmnt-dev"
    CONFIG_FILE="config_dev.json"
    SERVICE_ACCOUNT="redaction-tf-df@skyuk-uk-reg-expmnt-dev.iam.gserviceaccount.com"
    SUBNETWORK="https://www.googleapis.com/compute/v1/projects/skyuk-uk-shr-vpc-sc-ingt-dev/regions/europe-west1/subnetworks/sn-ds-ew1-ingt-dev-01-private"
    MAX_WORKERS="10"
    MACHINE_TYPE="n1-standard-4"
else
    PROJECT_ID="skyuk-uk-reg-expmnt-prod"  # UPDATE with your prod project
    CONFIG_FILE="config_prod.json"
    SERVICE_ACCOUNT="redaction-tf-df@${PROJECT_ID}.iam.gserviceaccount.com"  # UPDATE
    SUBNETWORK="https://www.googleapis.com/compute/v1/projects/skyuk-uk-shr-vpc-sc-ingt-prod/regions/europe-west1/subnetworks/sn-ds-ew1-ingt-prod-01-private"  # UPDATE
    MAX_WORKERS="20"
    MACHINE_TYPE="n1-standard-8"
fi

REGION="europe-west1"
TEMPLATE_BUCKET="dataflow-staging-europe-west1-181982885154"
TEMPLATE_PATH="gs://${TEMPLATE_BUCKET}/templates/pii-redaction-template.json"
JOB_NAME="pii-redaction-${ENV}-$(date +%Y%m%d-%H%M%S)"

echo "============================================"
echo "Running Dataflow Flex Template Job (${ENV^^})"
echo "============================================"
echo "Job Name: ${JOB_NAME}"
echo "Project: ${PROJECT_ID}"
echo "Template: ${TEMPLATE_PATH}"
echo "============================================"

# Check if config file exists
if [ ! -f "${CONFIG_FILE}" ]; then
    echo "Error: Config file ${CONFIG_FILE} not found!"
    exit 1
fi

# Upload config to GCS
CONFIG_GCS_PATH="gs://${TEMPLATE_BUCKET}/configs/$(basename ${CONFIG_FILE})"
echo ""
echo "Uploading config to GCS: ${CONFIG_GCS_PATH}"
gsutil cp ${CONFIG_FILE} ${CONFIG_GCS_PATH}

# Production confirmation
if [ "$ENV" = "prod" ]; then
    read -p "Deploy to PRODUCTION? (yes/no): " CONFIRM
    if [ "${CONFIRM}" != "yes" ]; then
        echo "Deployment cancelled."
        exit 0
    fi
fi

# Run the Flex Template
echo ""
echo "Launching Dataflow job..."
gcloud dataflow flex-template run ${JOB_NAME} \
    --template-file-gcs-location=${TEMPLATE_PATH} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --service-account-email=${SERVICE_ACCOUNT} \
    --subnetwork=${SUBNETWORK} \
    --max-workers=${MAX_WORKERS} \
    --worker-machine-type=${MACHINE_TYPE} \
    --parameters config_path=${CONFIG_GCS_PATH} \
    --parameters runner=DataflowRunner

echo ""
echo "============================================"
echo "✓ Job Submitted Successfully!"
echo "============================================"
echo "Job Name: ${JOB_NAME}"
echo ""
echo "Monitor at:"
echo "https://console.cloud.google.com/dataflow/jobs/${REGION}/${JOB_NAME}?project=${PROJECT_ID}"
echo ""
echo "Or run:"
echo "gcloud dataflow jobs describe ${JOB_NAME} --region=${REGION} --project=${PROJECT_ID}"
echo "============================================"
