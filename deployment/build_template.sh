#!/bin/bash

# Build and deploy Flex Template using Cloud Build
# This script submits the build to Cloud Build which handles:
# 1. Building Docker image with all dependencies
# 2. Pushing image to Artifact Registry
# 3. Creating Flex Template spec in GCS

set -e

PROJECT_ID="skyuk-uk-reg-expmnt-dev"
REGION="europe-west1"
ARTIFACT_REGISTRY="shared-redaction-app"
TEMPLATE_IMAGE="pii-redaction-flex-template"
GCS_BUCKET="dataflow-staging-europe-west1-181982885154"

echo "========================================="
echo "Building Flex Template with Cloud Build"
echo "========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Artifact Registry: $ARTIFACT_REGISTRY"
echo "Template Image: $TEMPLATE_IMAGE"
echo "GCS Bucket: $GCS_BUCKET"
echo "========================================="

# Verify Artifact Registry exists
echo "Verifying Artifact Registry..."
if ! gcloud artifacts repositories describe $ARTIFACT_REGISTRY \
    --project=$PROJECT_ID \
    --location=$REGION &> /dev/null; then
    echo "ERROR: Artifact Registry '$ARTIFACT_REGISTRY' not found in $REGION"
    exit 1
fi
echo "✓ Artifact Registry found"

# Submit build to Cloud Build
echo ""
echo "Submitting build to Cloud Build..."
gcloud builds submit \
    --config=deployment/cloudbuild.yaml \
    --project=$PROJECT_ID \
    --gcs-source-staging-dir=gs://$GCS_BUCKET/source

echo ""
echo "========================================="
echo "Build completed successfully!"
echo "========================================="
echo "Docker image: $REGION-docker.pkg.dev/$PROJECT_ID/$ARTIFACT_REGISTRY/$TEMPLATE_IMAGE:latest"
echo "Template spec: gs://$GCS_BUCKET/templates/$TEMPLATE_IMAGE.json"
echo ""
echo "Next steps:"
echo "1. Run dev job: ./deployment/run_template.sh dev"
echo "2. Run prod job: ./deployment/run_template.sh prod"
echo "========================================="
