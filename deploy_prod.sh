#!/bin/bash

# Deploy PII Redaction Flex Template Job - PRODUCTION
# This script launches a Dataflow job using the Flex Template

set -e  # Exit on error

# Configuration
PROJECT_ID="skyuk-uk-reg-expmnt-prod"  # UPDATE with your production project
REGION="europe-west1"
TEMPLATE_GCS_PATH="gs://dataflow-templates-${PROJECT_ID}/templates/pii-redaction/template_spec.json"

# Job configuration
JOB_NAME="pii-redaction-prod-$(date +%Y%m%d-%H%M%S)"
CONFIG_PATH="config_prod.json"

# Service Account - UPDATE with your production service account
SERVICE_ACCOUNT="redaction-tf-df@${PROJECT_ID}.iam.gserviceaccount.com"

# Network configuration - UPDATE with your production subnetwork
SUBNETWORK="https://www.googleapis.com/compute/v1/projects/skyuk-uk-shr-vpc-sc-ingt-prod/regions/europe-west1/subnetworks/sn-ds-ew1-ingt-prod-01-private"

# Worker configuration
MAX_WORKERS="20"
MACHINE_TYPE="n1-standard-8"

echo "============================================"
echo "Deploying PII Redaction Job (PROD)"
echo "============================================"
echo "Job Name: ${JOB_NAME}"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Config: ${CONFIG_PATH}"
echo "============================================"

# Check if config file exists
if [ ! -f "${CONFIG_PATH}" ]; then
    echo "Error: Config file ${CONFIG_PATH} not found!"
    exit 1
fi

# Confirmation prompt for production
read -p "Are you sure you want to deploy to PRODUCTION? (yes/no): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

# Option 1: Upload config to GCS (recommended for Flex Templates)
CONFIG_GCS_PATH="gs://dataflow-staging-europe-west1-PROD-BUCKET/configs/$(basename ${CONFIG_PATH})"  # UPDATE bucket name
echo ""
echo "Uploading config to GCS: ${CONFIG_GCS_PATH}"
gsutil cp ${CONFIG_PATH} ${CONFIG_GCS_PATH}

# Launch the Flex Template job
echo ""
echo "Launching Dataflow job..."
gcloud dataflow flex-template run ${JOB_NAME} \
    --template-file-gcs-location=${TEMPLATE_GCS_PATH} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --service-account-email=${SERVICE_ACCOUNT} \
    --subnetwork=${SUBNETWORK} \
    --max-workers=${MAX_WORKERS} \
    --worker-machine-type=${MACHINE_TYPE} \
    --parameters config_path=${CONFIG_GCS_PATH} \
    --parameters runner=DataflowRunner \
    --parameters log_level=WARNING

echo ""
echo "============================================"
echo "✓ Job Submitted Successfully!"
echo "============================================"
echo "Job Name: ${JOB_NAME}"
echo ""
echo "Monitor your job at:"
echo "https://console.cloud.google.com/dataflow/jobs/${REGION}/${JOB_NAME}?project=${PROJECT_ID}"
echo ""
echo "Or use:"
echo "gcloud dataflow jobs describe ${JOB_NAME} --region=${REGION} --project=${PROJECT_ID}"
echo "============================================"
