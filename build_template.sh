#!/bin/bash

# Build Flex Template using Cloud Build
# This eliminates the need for local Docker installation

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-skyuk-uk-reg-expmnt-dev}"
REGION="europe-west1"
TEMPLATE_BUCKET="${TEMPLATE_BUCKET:-dataflow-staging-europe-west1-181982885154}"
ARTIFACT_REGISTRY_REPO="shared-redaction-app"

echo "============================================"
echo "Building Flex Template via Cloud Build"
echo "============================================"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Artifact Registry: ${ARTIFACT_REGISTRY_REPO}"
echo "Template Bucket: gs://${TEMPLATE_BUCKET}"
echo "============================================"

# Step 1: Verify Artifact Registry repository exists
echo ""
echo "[1/3] Verifying Artifact Registry repository..."
if ! gcloud artifacts repositories describe ${ARTIFACT_REGISTRY_REPO} \
    --project=${PROJECT_ID} \
    --location=${REGION} &>/dev/null; then
    echo "Error: Artifact Registry repository '${ARTIFACT_REGISTRY_REPO}' not found!"
    echo "Please ensure the repository exists in ${REGION}"
    exit 1
else
    echo "Repository ${ARTIFACT_REGISTRY_REPO} found"
fi

# Step 2: Submit Cloud Build job
echo ""
echo "[2/3] Submitting Cloud Build job..."
echo "This will take 10-15 minutes (includes spaCy model download)..."

# Use staging bucket for Cloud Build source (you have write access there)
gcloud builds submit \
    --config=cloudbuild.yaml \
    --substitutions=_TEMPLATE_BUCKET=${TEMPLATE_BUCKET} \
    --gcs-source-staging-dir=gs://${TEMPLATE_BUCKET}/cloudbuild-source \
    --project=${PROJECT_ID} \
    --region=${REGION}

echo ""
echo "============================================"
echo "✓ Build Complete!"
echo "============================================"
echo "Template Location: gs://${TEMPLATE_BUCKET}/templates/pii-redaction-template.json"
echo ""
echo "To deploy, run:"
echo "./run_template.sh dev"
echo "or"
echo "./run_template.sh prod"
echo "============================================"
