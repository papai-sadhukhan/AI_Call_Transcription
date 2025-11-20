# Dataflow Flex Template Deployment Guide

This guide explains how to build, deploy, and run the PII Redaction Dataflow pipeline using Flex Templates.

## Overview

The pipeline has been migrated from direct Dataflow submission to Flex Templates, which provides:
- **Containerized Execution**: All dependencies pre-installed in Docker image
- **No Worker Startup Delays**: spaCy model (738 MB) is pre-downloaded
- **Version Control**: Immutable Docker images for reproducible deployments
- **Template Reusability**: Launch multiple jobs from the same template

## Prerequisites

1. **Docker Desktop** installed and running
2. **gcloud CLI** authenticated with appropriate permissions:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```
3. **Required GCP Permissions**:
   - Artifact Registry: `roles/artifactregistry.admin`
   - Cloud Storage: `roles/storage.admin`
   - Dataflow: `roles/dataflow.admin`
   - Service Account User: `roles/iam.serviceAccountUser`

## Architecture

```
┌─────────────────┐
│   Dockerfile    │ ──> Build ──> Docker Image ──> Artifact Registry
└─────────────────┘                                        │
                                                           │
┌─────────────────┐                                        │
│  metadata.json  │ ──> Upload ──> GCS Template Spec <────┘
└─────────────────┘                           │
                                              │
                                              ▼
                                    gcloud dataflow flex-template run
                                              │
                                              ▼
                                      Dataflow Job Execution
```

## Files Created

### 1. `Dockerfile`
Defines the container image with:
- Base: `gcr.io/dataflow-templates-base/python39-template-launcher-base`
- Python dependencies from `requirements.txt`
- Pre-downloaded spaCy model (`en_core_web_lg`)
- Application code (`main.py`, `utils/`, `redactConfig.yaml`)

### 2. `.dockerignore`
Excludes unnecessary files from Docker build context:
- `__pycache__/`, logs, test files
- Git/IDE files
- Build artifacts

### 3. `metadata.json`
Defines Flex Template parameters:
- `config_path`: Path to JSON configuration (required)
- `runner`: DataflowRunner or DirectRunner (optional)
- `log_level`: Logging verbosity (optional)
- GCP settings: project, region, staging, service account, etc.

### 4. `build_and_push.sh`
Automated script to:
1. Create Artifact Registry repository (if needed)
2. Configure Docker authentication
3. Build Docker image with version tagging
4. Push to Artifact Registry
5. Create and upload template spec to GCS

### 5. `deploy_dev.sh` / `deploy_prod.sh`
Environment-specific deployment scripts that:
1. Upload configuration file to GCS
2. Launch Dataflow job using Flex Template
3. Apply appropriate worker configuration
4. Provide job monitoring links

## Step-by-Step Deployment

### Step 1: Configure Environment Variables

Edit `build_and_push.sh` and set:
```bash
PROJECT_ID="your-project-id"
REGION="europe-west1"
REPOSITORY="dataflow-templates"
TEMPLATE_GCS_PATH="gs://your-bucket/templates/pii-redaction"
```

### Step 2: Build and Push Docker Image

```bash
# On Windows with Git Bash
bash build_and_push.sh

# Or set environment variables inline
GCP_PROJECT_ID="skyuk-uk-reg-expmnt-dev" \
GCP_REGION="europe-west1" \
VERSION="1.0.0" \
bash build_and_push.sh
```

This will:
- Build image: `europe-west1-docker.pkg.dev/PROJECT/dataflow-templates/pii-redaction-flex-template:1.0.0-TIMESTAMP`
- Tag as `latest`
- Upload template spec to GCS

**Build Time**: ~10-15 minutes (includes spaCy model download)

### Step 3: Deploy to Development

Edit `deploy_dev.sh` to verify settings, then:

```bash
bash deploy_dev.sh
```

This will:
1. Upload `config_dev.json` to GCS
2. Launch Dataflow job with dev configuration
3. Output job monitoring URL

### Step 4: Deploy to Production

Update production settings in `deploy_prod.sh`:
- Project ID
- Service account
- Subnetwork
- GCS bucket paths

Then deploy:

```bash
bash deploy_prod.sh
```

**Note**: Requires confirmation prompt for production deployments.

## Configuration Strategy

### Option A: File-Based (Current Approach)
- Configuration remains in `config_dev.json` / `config_prod.json`
- Scripts upload config to GCS before job submission
- Template parameter: `config_path=gs://bucket/config.json`

**Pros**: Minimal code changes, backward compatible  
**Cons**: Config must be uploaded to GCS for each run

### Option B: Parameterized (Future Enhancement)
- Expose individual settings as template parameters
- No config file needed
- Example: `--parameters project=X,dataset=Y,table=Z`

**Pros**: More flexible, better GitOps integration  
**Cons**: Requires main.py modifications

## Monitoring and Troubleshooting

### View Job Status
```bash
# List recent jobs
gcloud dataflow jobs list --region=europe-west1 --project=YOUR_PROJECT

# Describe specific job
gcloud dataflow jobs describe JOB_ID --region=europe-west1

# View logs
gcloud dataflow jobs logs JOB_ID --region=europe-west1
```

### Common Issues

**1. Docker Build Fails**
- Ensure Docker Desktop is running
- Check network connectivity (spaCy model download)
- Verify `requirements.txt` has no version conflicts

**2. Image Push Fails**
- Authenticate: `gcloud auth configure-docker REGION-docker.pkg.dev`
- Check Artifact Registry permissions
- Verify repository exists

**3. Job Launch Fails**
- Ensure template spec exists in GCS: `gsutil ls TEMPLATE_PATH`
- Verify service account has required permissions
- Check subnetwork configuration

**4. Worker Startup Errors**
- Review Dataflow job logs in Cloud Console
- Check for missing dependencies (all should be in Docker image)
- Verify spaCy model is pre-downloaded (no runtime download)

## Updating the Template

### Code Changes
1. Make changes to `main.py`, `utils/`, or `redactConfig.yaml`
2. Increment `VERSION` in `build_and_push.sh`
3. Run `bash build_and_push.sh`
4. New image is created with new version tag
5. Template spec is updated automatically

### Dependency Changes
1. Update `requirements.txt`
2. Rebuild image: `bash build_and_push.sh`
3. Docker layer caching speeds up builds

### Configuration Changes
- **Development**: Edit `config_dev.json`, run `bash deploy_dev.sh`
- **Production**: Edit `config_prod.json`, run `bash deploy_prod.sh`

## Migration from Old Approach

### Old Method (Direct Submission)
```bash
python main.py --config_path config_dev.json --runner DataflowRunner
```
- Workers install dependencies at startup using `setup.py`
- spaCy model downloaded per worker (738 MB, ~5-10 min delay)
- No version control of worker environment

### New Method (Flex Template)
```bash
bash deploy_dev.sh  # or deploy_prod.sh
```
- All dependencies pre-installed in Docker image
- spaCy model pre-downloaded (instant worker startup)
- Immutable image ensures consistency
- Can launch multiple jobs from same template

## Cost Optimization

1. **Reuse Images**: Tag with `latest` for development, use versioned tags for production
2. **Worker Configuration**: Adjust `max_num_workers` and `machine_type` per environment
3. **Image Size**: Current image ~2-3 GB (includes 738 MB spaCy model)
4. **Build Frequency**: Only rebuild when code/dependencies change

## Security Best Practices

1. **Service Account**: Use least-privilege service accounts
2. **VPC**: Deploy workers in private subnetwork
3. **Artifact Registry**: Restrict access with IAM roles
4. **Config Files**: Store sensitive values in Secret Manager (future enhancement)
5. **Image Scanning**: Enable vulnerability scanning in Artifact Registry

## Next Steps

1. **Test in Development**: Run a small job with `limit=100` in `config_dev.json`
2. **Validate Output**: Check BigQuery target table for correct redactions
3. **Performance Testing**: Compare worker startup time vs. old approach
4. **Production Rollout**: Deploy with production configuration
5. **Monitoring**: Set up alerts for job failures in Cloud Monitoring

## Support

For issues or questions:
1. Check Dataflow job logs in Cloud Console
2. Review this documentation
3. Contact the team or raise an issue in the repository

---

**Migration completed**: November 20, 2025
**Version**: 1.0.0
