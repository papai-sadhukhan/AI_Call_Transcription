#!/bin/bash

# Flex Template Build and Push Script
# This script builds the Docker image, pushes it to Artifact Registry,
# and creates the Flex Template spec file in GCS

set -e  # Exit on error

# Configuration - UPDATE THESE VALUES
PROJECT_ID="${GCP_PROJECT_ID:-skyuk-uk-reg-expmnt-dev}"
REGION="${GCP_REGION:-europe-west1}"
REPOSITORY="${ARTIFACT_REGISTRY_REPO:-dataflow-templates}"
IMAGE_NAME="pii-redaction-flex-template"
TEMPLATE_GCS_PATH="${TEMPLATE_GCS_PATH:-gs://dataflow-templates-${PROJECT_ID}/templates/pii-redaction}"

# Version and timestamp for image tagging
VERSION="${VERSION:-1.0.0}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
IMAGE_TAG="${VERSION}-${TIMESTAMP}"

# Full image URI
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"
IMAGE_URI_LATEST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:latest"

echo "============================================"
echo "Building Flex Template for PII Redaction"
echo "============================================"
echo "Project ID: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Image URI: ${IMAGE_URI}"
echo "Template GCS Path: ${TEMPLATE_GCS_PATH}"
echo "============================================"

# Step 1: Create Artifact Registry repository if it doesn't exist
echo ""
echo "[1/5] Checking Artifact Registry repository..."
if ! gcloud artifacts repositories describe ${REPOSITORY} \
    --project=${PROJECT_ID} \
    --location=${REGION} &>/dev/null; then
    echo "Creating Artifact Registry repository: ${REPOSITORY}"
    gcloud artifacts repositories create ${REPOSITORY} \
        --repository-format=docker \
        --location=${REGION} \
        --description="Dataflow Flex Templates" \
        --project=${PROJECT_ID}
else
    echo "Repository ${REPOSITORY} already exists"
fi

# Step 2: Configure Docker to use gcloud credentials
echo ""
echo "[2/5] Configuring Docker authentication..."
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

# Step 3: Build the Docker image
echo ""
echo "[3/5] Building Docker image..."
docker build -t ${IMAGE_URI} -t ${IMAGE_URI_LATEST} .

# Step 4: Push the Docker image to Artifact Registry
echo ""
echo "[4/5] Pushing Docker image to Artifact Registry..."
docker push ${IMAGE_URI}
docker push ${IMAGE_URI_LATEST}

# Step 5: Create the Flex Template spec file
echo ""
echo "[5/5] Creating Flex Template spec file..."

TEMPLATE_SPEC_FILE="template_spec.json"

cat > ${TEMPLATE_SPEC_FILE} <<EOF
{
  "image": "${IMAGE_URI}",
  "metadata": {
    "name": "PII Redaction Dataflow Pipeline",
    "description": "Flex Template for redacting PII from BigQuery conversation transcripts using Presidio and custom recognizers",
    "parameters": [
      {
        "name": "config_path",
        "label": "Configuration File Path",
        "helpText": "Path to the JSON configuration file (local or GCS path like gs://bucket/config.json)",
        "isOptional": false,
        "regexes": ["^.+\\\\.json$"],
        "paramType": "TEXT"
      },
      {
        "name": "runner",
        "label": "Pipeline Runner",
        "helpText": "The runner to use for executing the pipeline (DataflowRunner or DirectRunner)",
        "isOptional": true,
        "regexes": ["^(DataflowRunner|DirectRunner)$"],
        "paramType": "TEXT"
      },
      {
        "name": "log_level",
        "label": "Logging Level",
        "helpText": "Logging level for the pipeline (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        "isOptional": true,
        "regexes": ["^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"],
        "paramType": "TEXT"
      }
    ],
    "streaming": false
  },
  "sdkInfo": {
    "language": "PYTHON"
  }
}
EOF

# Upload template spec to GCS
echo "Uploading template spec to ${TEMPLATE_GCS_PATH}/template_spec.json"
gsutil cp ${TEMPLATE_SPEC_FILE} ${TEMPLATE_GCS_PATH}/template_spec.json

# Also copy metadata.json to GCS for reference
echo "Uploading metadata.json to ${TEMPLATE_GCS_PATH}/metadata.json"
gsutil cp metadata.json ${TEMPLATE_GCS_PATH}/metadata.json

echo ""
echo "============================================"
echo "✓ Build and Push Complete!"
echo "============================================"
echo "Image URI: ${IMAGE_URI}"
echo "Latest Tag: ${IMAGE_URI_LATEST}"
echo "Template Spec: ${TEMPLATE_GCS_PATH}/template_spec.json"
echo ""
echo "To run the template, use:"
echo "gcloud dataflow flex-template run JOB_NAME \\"
echo "  --template-file-gcs-location=${TEMPLATE_GCS_PATH}/template_spec.json \\"
echo "  --region=${REGION} \\"
echo "  --parameters config_path=gs://your-bucket/config.json"
echo "============================================"
