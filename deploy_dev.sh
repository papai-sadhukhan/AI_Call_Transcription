#!/bin/bash

# Deploy PII Redaction Flex Template Job - DEVELOPMENT
# This script launches a Dataflow job using the Flex Template

set -e  # Exit on error

# Configuration
PROJECT_ID="skyuk-uk-reg-expmnt-dev"
REGION="europe-west1"
TEMPLATE_GCS_PATH="gs://dataflow-templates-${PROJECT_ID}/templates/pii-redaction/template_spec.json"

# Job configuration
JOB_NAME="pii-redaction-dev-$(date +%Y%m%d-%H%M%S)"
CONFIG_PATH="config_dev.json"

# Service Account
SERVICE_ACCOUNT="redaction-tf-df@skyuk-uk-reg-expmnt-dev.iam.gserviceaccount.com"

# Network configuration
SUBNETWORK="https://www.googleapis.com/compute/v1/projects/skyuk-uk-shr-vpc-sc-ingt-dev/regions/europe-west1/subnetworks/sn-ds-ew1-ingt-dev-01-private"

# Worker configuration
MAX_WORKERS="10"
MACHINE_TYPE="n1-standard-4"

echo "============================================"
echo "Deploying PII Redaction Job (DEV)"
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

# Option 1: Upload config to GCS (recommended for Flex Templates)
CONFIG_GCS_PATH="gs://dataflow-staging-europe-west1-181982885154/configs/$(basename ${CONFIG_PATH})"
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
    --parameters log_level=INFO

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
