# Dataflow Flex Template - Cloud Build Deployment

## Overview

This project uses **Cloud Build** to create Dataflow Flex Templates, eliminating the need for local Docker installation.

## Architecture

```
Local Files → Cloud Build → Docker Image → Artifact Registry
                    ↓
              Flex Template → GCS
                    ↓
            gcloud dataflow run → Dataflow Job
```

## Files

- **`Dockerfile`**: Container definition with Python dependencies and spaCy model
- **`cloudbuild.yaml`**: Cloud Build configuration (builds image, creates template)
- **`metadata.json`**: Flex Template parameter definitions
- **`build_template.sh`**: Submit Cloud Build job to create template
- **`run_template.sh`**: Launch Dataflow job from template

## Quick Start

### 1. Enable Required APIs

```bash
gcloud services enable cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    dataflow.googleapis.com \
    --project=skyuk-uk-reg-expmnt-dev
```

### 2. Build Template (One-time or when code changes)

```bash
# From your local VS Code terminal (no Docker needed!)
bash build_template.sh
```

This triggers Cloud Build to:
- Build Docker image with all dependencies
- Pre-download spaCy model (738 MB)
- Push to Artifact Registry
- Create Flex Template in GCS

**Build time**: ~10-15 minutes

### 3. Run Pipeline

```bash
# Development
bash run_template.sh dev

# Production
bash run_template.sh prod
```

## Configuration

### Environment Variables (Optional)

```bash
# Override defaults
export GCP_PROJECT_ID="your-project-id"
export TEMPLATE_BUCKET="your-bucket-name"

bash build_template.sh
```

### Update Production Settings

Edit `run_template.sh` lines 20-26 for production:
- Project ID
- Service Account
- Subnetwork
- Worker configuration

## Cloud Build Pricing

- **First 120 build-minutes/day**: Free
- **Additional**: $0.003/build-minute
- **Typical build**: ~15 minutes = $0.045 (after free tier)

## Troubleshooting

### Build fails with permission error

```bash
# Grant Cloud Build service account necessary permissions
PROJECT_NUMBER=$(gcloud projects describe skyuk-uk-reg-expmnt-dev --format='value(projectNumber)')
gcloud projects add-iam-policy-binding skyuk-uk-reg-expmnt-dev \
    --member=serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com \
    --role=roles/artifactregistry.writer

gcloud projects add-iam-policy-binding skyuk-uk-reg-expmnt-dev \
    --member=serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com \
    --role=roles/storage.objectAdmin
```

### View build logs

```bash
gcloud builds list --project=skyuk-uk-reg-expmnt-dev
gcloud builds log BUILD_ID --project=skyuk-uk-reg-expmnt-dev
```

### Template not found

Verify template exists:
```bash
gsutil ls gs://dataflow-staging-europe-west1-181982885154/templates/
```

## Benefits

✅ **No local Docker required**  
✅ **Works from Windows/Mac/Linux**  
✅ **Automated builds**  
✅ **CI/CD ready**  
✅ **Consistent builds**  
✅ **Free tier available**  

## Workflow

### For Code Changes

1. Edit code locally
2. Run `bash build_template.sh` (rebuilds template)
3. Run `bash run_template.sh dev` (launches job)

### For Config Changes Only

1. Edit `config_dev.json` or `config_prod.json`
2. Run `bash run_template.sh dev` (no rebuild needed)

## Next Steps

1. Run `bash build_template.sh` to create your first template
2. Test with `bash run_template.sh dev`
3. Monitor job in Cloud Console
4. Deploy to prod with `bash run_template.sh prod`
