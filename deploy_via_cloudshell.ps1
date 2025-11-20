# Deploy Flex Template via Cloud Shell from Local VS Code Terminal
# This script runs all commands in Cloud Shell without needing local Docker

param(
    [string]$ProjectId = "skyuk-uk-reg-expmnt-dev",
    [string]$Region = "europe-west1",
    [string]$RepoUrl = "https://github.com/sky-uk/skydata-genai-tf.git",
    [string]$Branch = "redaction"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Deploying via Cloud Shell" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Project: $ProjectId"
Write-Host "Repository: $RepoUrl"
Write-Host "Branch: $Branch"
Write-Host "============================================" -ForegroundColor Cyan

# Function to run commands in Cloud Shell
function Invoke-CloudShellCommand {
    param([string]$Command)
    Write-Host ""
    Write-Host "Running in Cloud Shell: $Command" -ForegroundColor Yellow
    gcloud cloud-shell ssh --command="$Command"
}

Write-Host ""
Write-Host "[1/6] Testing Cloud Shell connectivity..." -ForegroundColor Green
Invoke-CloudShellCommand "echo 'Cloud Shell connected successfully'"

Write-Host ""
Write-Host "[2/6] Setting up project configuration..." -ForegroundColor Green
Invoke-CloudShellCommand "gcloud config set project $ProjectId"

Write-Host ""
Write-Host "[3/6] Cloning repository (or updating if exists)..." -ForegroundColor Green
$cloneCmd = @"
if [ -d skydata-genai-tf ]; then
    cd skydata-genai-tf && git fetch && git checkout $Branch && git pull
else
    git clone $RepoUrl && cd skydata-genai-tf && git checkout $Branch
fi
"@
Invoke-CloudShellCommand $cloneCmd

Write-Host ""
Write-Host "[4/6] Setting permissions..." -ForegroundColor Green
Invoke-CloudShellCommand "cd skydata-genai-tf && chmod +x *.sh"

Write-Host ""
Write-Host "[5/6] Building and pushing Docker image..." -ForegroundColor Green
Write-Host "This will take 10-15 minutes (downloading spaCy model)..." -ForegroundColor Yellow
Invoke-CloudShellCommand "cd skydata-genai-tf && bash build_and_push.sh"

Write-Host ""
Write-Host "[6/6] Deploying to Dataflow..." -ForegroundColor Green
Invoke-CloudShellCommand "cd skydata-genai-tf && bash deploy_dev.sh"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "✓ Deployment Complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To monitor your job, run:"
Write-Host "gcloud dataflow jobs list --region=$Region --project=$ProjectId" -ForegroundColor Yellow
Write-Host ""
Write-Host "Or visit Cloud Console:"
Write-Host "https://console.cloud.google.com/dataflow/jobs?project=$ProjectId" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
