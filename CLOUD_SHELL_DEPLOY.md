# Deploy via Google Cloud Shell (No Local Docker Needed)

## Step 1: Open Cloud Shell

1. Go to **Google Cloud Console**: https://console.cloud.google.com
2. Select project: `skyuk-uk-reg-expmnt-dev`
3. Click **Activate Cloud Shell** button (terminal icon in top-right toolbar)
4. Wait for Cloud Shell to initialize (~30 seconds)

## Step 2: Clone Your Repository

```bash
# Clone your repository
git clone https://github.com/sky-uk/skydata-genai-tf.git

# Navigate to project
cd skydata-genai-tf

# Switch to your branch
git checkout redaction
```

**Alternative: If repo is private and needs authentication**
```bash
# Use personal access token or SSH key
git clone https://<TOKEN>@github.com/sky-uk/skydata-genai-tf.git
```

## Step 3: Verify Files

```bash
# List all files to confirm
ls -la

# Should see: Dockerfile, build_and_push.sh, deploy_dev.sh, etc.
cat Dockerfile  # Quick check
```

## Step 4: Configure and Build

```bash
# Set execute permissions
chmod +x build_and_push.sh deploy_dev.sh deploy_prod.sh

# Verify Docker is available (Cloud Shell has it pre-installed)
docker --version

# Run the build script
bash build_and_push.sh
```

**Build process will:**
- Create Artifact Registry repository (if needed)
- Build Docker image (~10-15 minutes due to spaCy model download)
- Push to Artifact Registry
- Upload template spec to GCS

## Step 5: Deploy to Dataflow

```bash
# Deploy development job
bash deploy_dev.sh
```

**The script will:**
- Upload `config_dev.json` to GCS
- Launch Dataflow job with Flex Template
- Display job monitoring URL

## Step 6: Monitor Job

Click the URL provided, or run:
```bash
# List recent jobs
gcloud dataflow jobs list --region=europe-west1

# Get specific job details
gcloud dataflow jobs describe <JOB_ID> --region=europe-west1

# Stream logs
gcloud dataflow jobs logs <JOB_ID> --region=europe-west1
```

## Troubleshooting in Cloud Shell

**Issue: Permission denied**
```bash
# Ensure you're authenticated
gcloud auth list

# If needed, login
gcloud auth login
```

**Issue: Wrong project**
```bash
# Set correct project
gcloud config set project skyuk-uk-reg-expmnt-dev

# Verify
gcloud config get-value project
```

**Issue: Git credentials**
```bash
# If clone fails with private repo
# Generate personal access token at: https://github.com/settings/tokens
# Then use: git clone https://<USERNAME>:<TOKEN>@github.com/sky-uk/skydata-genai-tf.git
```

**Issue: Need to update code**
```bash
# Make changes in Cloud Shell Editor (click "Open Editor" button)
# Or pull latest changes
git pull origin redaction
```

## Future Deployments

Once built, you only need:

```bash
# Open Cloud Shell
cd skydata-genai-tf

# Pull latest changes (if any)
git pull

# Rebuild only if code changed
bash build_and_push.sh  # Only when code/dependencies change

# Deploy
bash deploy_dev.sh      # For dev
bash deploy_prod.sh     # For prod
```

## Advantages of Cloud Shell

✅ Docker pre-installed  
✅ gcloud pre-authenticated  
✅ No local machine requirements  
✅ Fast network to GCP services  
✅ 5GB persistent home directory  
✅ Free to use  

## Cost Note

- Cloud Shell: **Free**
- Docker image storage in Artifact Registry: **~$0.10/GB/month**
- Dataflow job execution: **Pay per worker hour** (standard Dataflow pricing)

---

**Ready to start?** Open Cloud Console and activate Cloud Shell!
