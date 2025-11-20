#!/bin/bash

# Deploy Flex Template via Cloud Shell from Local VS Code Terminal
# This script runs all commands in Cloud Shell without needing local Docker

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-skyuk-uk-reg-expmnt-dev}"
REGION="europe-west1"
REPO_URL="https://github.com/sky-uk/skydata-genai-tf.git"
BRANCH="redaction"

echo "============================================"
echo "Deploying via Cloud Shell"
echo "============================================"
echo "Project: ${PROJECT_ID}"
echo "Repository: ${REPO_URL}"
echo "Branch: ${BRANCH}"
echo "============================================"

# Function to run commands in Cloud Shell
run_in_cloud_shell() {
    echo ""
    echo "Running in Cloud Shell: $1"
    gcloud cloud-shell ssh --command="$1"
}

echo ""
echo "[1/6] Testing Cloud Shell connectivity..."
run_in_cloud_shell "echo 'Cloud Shell connected successfully'"

echo ""
echo "[2/6] Setting up project configuration..."
run_in_cloud_shell "gcloud config set project ${PROJECT_ID}"

echo ""
echo "[3/6] Cloning repository (or updating if exists)..."
run_in_cloud_shell "
if [ -d skydata-genai-tf ]; then
    cd skydata-genai-tf && git fetch && git checkout ${BRANCH} && git pull
else
    git clone ${REPO_URL} && cd skydata-genai-tf && git checkout ${BRANCH}
fi
"

echo ""
echo "[4/6] Setting permissions..."
run_in_cloud_shell "cd skydata-genai-tf && chmod +x *.sh"

echo ""
echo "[5/6] Building and pushing Docker image..."
echo "This will take 10-15 minutes (downloading spaCy model)..."
run_in_cloud_shell "cd skydata-genai-tf && bash build_and_push.sh"

echo ""
echo "[6/6] Deploying to Dataflow..."
run_in_cloud_shell "cd skydata-genai-tf && bash deploy_dev.sh"

echo ""
echo "============================================"
echo "✓ Deployment Complete!"
echo "============================================"
echo ""
echo "To monitor your job, run:"
echo "gcloud dataflow jobs list --region=${REGION} --project=${PROJECT_ID}"
echo ""
echo "Or visit Cloud Console:"
echo "https://console.cloud.google.com/dataflow/jobs?project=${PROJECT_ID}"
echo "============================================"
