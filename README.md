# Call Transcript PII Redaction Pipeline

Dataflow pipeline for redacting Personally Identifiable Information (PII) from call transcripts using Microsoft Presidio, spaCy NLP, and custom context-aware entity recognizers.

## Overview

This pipeline processes conversation transcripts from BigQuery, detects and redacts 20+ types of PII entities, and writes the anonymized transcripts back to BigQuery. It uses a stateful approach with conversation context tracking to improve accuracy, particularly for multi-turn conversations where sensitive information spans multiple exchanges between agent and customer.

### Key Features

- **Stateful PII Detection**: 9 custom entity recognizers with conversation context tracking
- **Microsoft Presidio Framework**: Industry-standard PII detection and anonymization  
- **spaCy NLP Model**: `en_core_web_lg` (738 MB) for advanced language understanding
- **False Positive Filtering**: Configurable deny lists and conversational word validation
- **BigQuery I/O**: Batch processing with configurable limits and streaming inserts
- **Flex Template Deployment**: Cloud Build-based CI/CD with Artifact Registry

### Supported PII Entities

| Entity Type | Example | Redaction Placeholder |
|------------|---------|----------------------|
| PERSON | "John Smith" | [REDACTED NAME] |
| EMAIL_ADDRESS | "user@example.com" | [REDACTED EMAIL] |
| PHONE_NUMBER | "07123456789" | [REDACTED PHONE] |
| UK_POSTCODE | "SW1A 1AA" | [REDACTED POSTCODE] |
| ADDRESS | "123 Main Street" | [REDACTED ADDRESS] |
| CREDIT_CARD | "4111111111111111" | [REDACTED CARD] |
| ACCOUNT_NUMBER | "12345678" | [REDACTED ACCOUNT] |
| PASSWORD | Security codes/PINs | [REDACTED PASSWORD] |
| REFERENCE_NUMBER | Order/ticket numbers | [REDACTED REFERENCE] |
| BANK_ACCOUNT_LAST_DIGITS | "...12" | [REDACTED ACCOUNT DIGITS] |
| FINANCIAL_AMOUNT | "£149.99" | [REDACTED AMOUNT] |
| AGE | "35 years old" | [REDACTED AGE] |
| LOCATION | City/region names | [REDACTED LOCATION] |
| And 7 more... | | |

## Project Structure

```
skydata-genai-tf/
├── config/                          # Configuration files
│   ├── config_dev.json             # Dev environment config (100 record limit)
│   ├── config_prod.json            # Prod environment config (full dataset)
│   ├── redactConfig.yaml           # PII detection rules (deny list, scores, word lists)
│   └── setup.py                    # Python package setup for Dataflow workers
│
├── deployment/                      # Deployment artifacts
│   ├── Dockerfile                  # Container definition for Flex Template
│   ├── .dockerignore               # Docker build exclusions
│   ├── cloudbuild.yaml             # Cloud Build configuration
│   ├── metadata.json               # Flex Template parameter definitions
│   ├── build_template.sh           # Build and deploy template script
│   └── run_template.sh             # Run Dataflow job script
│
├── utils/                           # Custom PII recognizers
│   ├── __init__.py
│   ├── entity_recognizers.py      # 9 stateful recognizers + context tracker
│   └── logging_config.py          # Logging configuration
│
├── main.py                         # Apache Beam pipeline entry point
├── requirements.txt                # Python dependencies
├── README.md                       # This file
└── .gitignore                      # Git exclusions
```

## Environment Setup

### Prerequisites

- **Google Cloud Project**: `skyuk-uk-reg-expmnt-dev`
- **Region**: `europe-west1`
- **Required APIs**: Dataflow, Cloud Build, Artifact Registry, BigQuery
- **Service Accounts**:
  - `redaction-tf-df@skyuk-uk-reg-expmnt-dev.iam.gserviceaccount.com` (Dataflow runner)
  - `181982885154-compute@developer.gserviceaccount.com` (Cloud Build)
- **Artifact Registry**: `shared-redaction-app` (Docker repository)
- **GCS Bucket**: `gs://dataflow-staging-europe-west1-181982885154`

### Local Development Setup

1. **Clone Repository**
   ```bash
   git clone <repository-url>
   cd skydata-genai-tf
   ```

2. **Authenticate with GCP**
   ```bash
   gcloud auth login
   gcloud config set project skyuk-uk-reg-expmnt-dev
   ```

3. **Install Python Dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python -m spacy download en_core_web_lg
   ```

4. **Verify Configuration**
   ```bash
   # Check Artifact Registry access
   gcloud artifacts repositories describe shared-redaction-app \
     --location=europe-west1
   
   # Check BigQuery tables
   bq show skyuk-uk-reg-expmnt-dev:uk_call_transcript_exprmnt.td_call_redaction_p1
   ```

## Running the Pipeline

### Option 1: Production Deployment (Dataflow + Flex Template)

This is the **recommended approach** for production workloads.

#### Step 1: Build Flex Template

```bash
# Builds Docker image, pushes to Artifact Registry, creates template spec
./deployment/build_template.sh
```

**What happens:**
- Cloud Build builds container with all dependencies (including 738 MB spaCy model)
- Image pushed to `europe-west1-docker.pkg.dev/skyuk-uk-reg-expmnt-dev/shared-redaction-app/pii-redaction-flex-template:latest`
- Template spec created at `gs://dataflow-staging-europe-west1-181982885154/templates/pii-redaction-flex-template.json`

#### Step 2: Run Dataflow Job

**Development (100 records):**
```bash
./deployment/run_template.sh dev
```

**Production (full dataset):**
```bash
./deployment/run_template.sh prod
```

**Monitoring:**
```bash
# View job in console
gcloud dataflow jobs list --region=europe-west1

# Stream logs
gcloud dataflow jobs logs <JOB_ID> --region=europe-west1
```

### Option 2: Local Testing (DirectRunner)

For development and debugging, run the pipeline locally:

```bash
python main.py \
  --config_path=config/config_dev.json \
  --runner=DirectRunner \
  --log_level=DEBUG
```

**Note:** DirectRunner downloads data locally and processes in-memory. Not suitable for large datasets (use `limit: 100` in config).

### Option 3: Direct Dataflow Submission (No Template)

Submit job directly to Dataflow without building a template:

```bash
python main.py \
  --config_path=config/config_prod.json \
  --runner=DataflowRunner \
  --project=skyuk-uk-reg-expmnt-dev \
  --region=europe-west1 \
  --staging_location=gs://dataflow-staging-europe-west1-181982885154/staging \
  --temp_location=gs://dataflow-staging-europe-west1-181982885154/temp \
  --service_account_email=redaction-tf-df@skyuk-uk-reg-expmnt-dev.iam.gserviceaccount.com
```

## Configuration Guide

### Environment Configs (`config/config_dev.json` / `config/config_prod.json`)

```json
{
  "project": {
    "bigquery_project_id": "skyuk-uk-reg-expmnt-dev",
    "dataflow_project_id": "skyuk-uk-reg-expmnt-dev",
    "region": "europe-west1",
    "staging_location": "gs://...",
    "service_account_email": "..."
  },
  "dataset": {
    "input": "uk_call_transcript_exprmnt",  // or "cdn10" for prod
    "output": "uk_call_transcript_exprmnt"
  },
  "tables": {
    "source": {
      "name": "td_call_redaction_p1",
      "columns": {
        "transaction_id": "transaction_id",
        "input_transcript": "transcription"
      }
    },
    "target": {
      "name": "td_call_redaction_p2"
    }
  },
  "processing": {
    "limit": 100,  // Dev: 100, Prod: 999999999
    "batch_size": 300,
    "condition": "1=1"
  },
  "pii_entities": {
    "PERSON": "[REDACTED NAME]",
    "EMAIL_ADDRESS": "[REDACTED EMAIL]",
    // ... 18 more entity types
  },
  "context_indicators": {
    "name": ["NAME", "CALLED", "SURNAME"],
    "address": ["ADDRESS", "FIRST LINE", "FLAT"],
    "postcode": ["POSTCODE", "POSTAL CODE"],
    // ... 7 more indicator groups
  }
}
```

**Key Configuration Options:**

- **`limit`**: Number of records to process (100 for dev, 999999999 for prod)
- **`batch_size`**: BigQuery write batch size (300 recommended)
- **`service_account_email`**: Dataflow runner identity
- **`context_indicators`**: Keywords that trigger context-aware detection

### PII Detection Config (`config/redactConfig.yaml`)

```yaml
# spaCy model configuration
nlp_engine_name: spacy
models:
  - lang_code: en
    model_name: en_core_web_lg

# Deny list - words NOT to redact (179 common conversational words)
deny_list:
  - THE
  - AND
  - YOUR
  # ... 176 more

# Number words for spoken digit detection
number_words:
  - ZERO
  - ONE
  - TWO
  # ... 27 more

# Validation settings
validation:
  person_entity:
    enabled: true
    max_conversational_ratio: 0.5  # Reject if >50% conversational words

# Detection score thresholds
detection_scores:
  min_score_threshold: 0.7  # Minimum confidence score
```

**Configuration Purposes:**

- **`deny_list`**: Prevents false positives (e.g., "YOU'RE CAN'T" detected as PERSON)
- **`number_words`**: Recognizes spelled-out numbers ("ONE TWO THREE" → digits)
- **`validation`**: Smart filtering for default recognizer outputs
- **`detection_scores`**: Confidence threshold for entity detection

## PII Detection Logic

### Architecture: Stateful Entity Recognition

The pipeline uses a **stateful approach** with conversation context tracking:

1. **ConversationContextTracker**: Maintains state across conversation turns
   - Tracks last agent utterance
   - Sets expectation flags (expecting_name, expecting_address, etc.)
   - Provides context to all recognizers

2. **9 Custom Recognizers**: Each implements stateful detection logic
   - `StatefulReferenceNumberRecognizer`: Order/ticket numbers after context indicators
   - `StatefulBankDigitsRecognizer`: Last 2 digits of account numbers
   - `StatefulCardDigitsRecognizer`: Last 4 digits of card numbers
   - `StatefulNameRecognizer`: Names after "Can I have your name?" type prompts
   - `StatefulAddressRecognizer`: Addresses including street indicators and postcodes
   - `StatefulPostcodeRecognizer`: UK postcode patterns (e.g., "SW1A 1AA")
   - `StatefulEmailRecognizer`: Email addresses after context indicators
   - `StatefulPasswordRecognizer`: Security codes/passwords after prompts
   - `StatefulPhoneNumberRecognizer`: Phone numbers after context indicators

3. **Default Presidio Recognizers**: Baseline NER models (SpacyRecognizer, etc.)
   - Filtered by deny list and conversational ratio validation
   - Catches PII missed by custom recognizers

### Detection Flow Example

**Conversation Turn:**
```
Agent: "Can I have your postcode please?"
Customer: "SW1A 1AA"
```

**Processing:**
1. Agent turn analyzed → `context_tracker.expecting_postcode = True`
2. Customer turn analyzed → `StatefulPostcodeRecognizer` detects "SW1A 1AA" (high confidence)
3. Result filtered by score threshold (0.7)
4. Anonymized: `Customer: "[REDACTED POSTCODE]"`

### False Positive Prevention

**Problem:** Default NER models detect "YOU'RE CAN'T" as PERSON (false positive)

**Solution:**
1. **Deny List Matching**: Exact word matches in `deny_list` → skip
2. **Conversational Ratio Validation**: If >50% of words are conversational → skip
3. **Context-Based Filtering**: Only validate when NOT expecting a name

**Example:**
```python
# "YOU'RE CAN'T" detected by SpacyRecognizer
matched_text = "YOU'RE CAN'T"
conversational_ratio = 2/2 = 1.0  # 100% conversational
if conversational_ratio > 0.5:
    # Reject detection
```

## BigQuery Schema

### Source Table (`td_call_redaction_p1`)

| Column | Type | Description |
|--------|------|-------------|
| transaction_id | STRING | Unique call identifier |
| transaction_identifier | STRING | Alternative identifier |
| file_date | DATE | Transcript date |
| transcription | JSON | Conversation array: `[{"role":"agent","content":"..."}]` |

### Target Table (`td_call_redaction_p2`)

| Column | Type | Description |
|--------|------|-------------|
| file_date | DATE | Transcript date |
| transaction_id | STRING | Unique call identifier |
| transcription_redacted | JSON | Redacted conversation array |
| redacted_entity | STRING | Audit trail: detected entities with scores |
| load_dt | TIMESTAMP | Processing timestamp |

**Example `redacted_entity`:**
```
[agent] PERSON: John Smith (score: 0.85); [customer] PHONE_NUMBER: 07123456789 (score: 0.95)
```

## Troubleshooting

### Common Issues

**1. Permission Denied - Artifact Registry**
```
ERROR: denied: Permission "artifactregistry.repositories.downloadArtifacts" denied
```
**Solution:** Grant Artifact Registry Reader role to Dataflow service account:
```bash
gcloud artifacts repositories add-iam-policy-binding shared-redaction-app \
  --location=europe-west1 \
  --member="serviceAccount:redaction-tf-df@skyuk-uk-reg-expmnt-dev.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
```

**2. Cloud Build Submission Failed**
```
ERROR: User [papai.sadhukhan@sky.uk] does not have permission to submit builds
```
**Solution:** Use Cloud Build service account instead:
```bash
# build_template.sh already uses this:
serviceAccount: '181982885154-compute@developer.gserviceaccount.com'
```

**3. spaCy Model Not Found on Workers**
```
OSError: [E050] Can't find model 'en_core_web_lg'
```
**Solution:** Model is pre-downloaded in Dockerfile. Rebuild template:
```bash
./deployment/build_template.sh
```

**4. BigQuery Temp Table Conflicts**
```
Error: temp table beam_temp_table_xxx already exists
```
**Solution:** Pipeline auto-cleans temp tables before execution. If persisting, manually delete:
```bash
bq rm -f skyuk-uk-reg-expmnt-dev:dataflow_temp_dataset.beam_temp_table_*
```

**5. Pipeline Runs But No Redactions**
```
All conversations processed but entities still visible
```
**Solution:** Check detection scores in logs:
```bash
# Look for "Detected ENTITY_TYPE: 'text' (score: X.XX)"
# If scores < 0.7, adjust min_score_threshold in config/redactConfig.yaml
```

### Debugging Commands

```bash
# Check Dataflow job status
gcloud dataflow jobs list --region=europe-west1 --status=active

# Stream worker logs
gcloud dataflow jobs logs <JOB_ID> --region=europe-west1

# Test locally with verbose logging
python main.py \
  --config_path=config/config_dev.json \
  --runner=DirectRunner \
  --log_level=DEBUG

# Verify BigQuery output
bq query --use_legacy_sql=false \
  'SELECT transaction_id, redacted_entity 
   FROM `skyuk-uk-reg-expmnt-dev.uk_call_transcript_exprmnt.td_call_redaction_p2` 
   LIMIT 10'
```

## Performance Considerations

- **spaCy Model**: 738 MB model pre-downloaded in container (adds ~2 min to build time)
- **Batch Size**: 300 records per BigQuery write (configurable in `config`)
- **Worker Autoscaling**: Dataflow auto-scales based on workload
- **Processing Rate**: ~100-200 transcripts/min on n1-standard-4 workers
- **Cost Optimization**: Use `limit` in dev config to avoid processing full dataset during testing

## Maintenance

### Updating PII Entity Mappings

Edit `config/config_dev.json` or `config/config_prod.json`:

```json
"pii_entities": {
  "NEW_ENTITY_TYPE": "[REDACTED NEW_TYPE]"
}
```

Rebuild template:
```bash
./deployment/build_template.sh
```

### Updating Deny List

Edit `config/redactConfig.yaml`:

```yaml
deny_list:
  - EXISTING_WORD
  - NEW_WORD_TO_EXCLUDE
```

Rebuild template and redeploy.

### Updating spaCy Model Version

Edit `requirements.txt`:
```
spacy==3.8.0  # Update version
```

Edit `deployment/Dockerfile`:
```dockerfile
RUN python -m spacy download en_core_web_lg
```

Rebuild template.

## Contributing

When adding new recognizers:

1. Implement in `utils/entity_recognizers.py` following `StatefulEntityRecognizer` pattern
2. Register in `main.py` → `EntityRecognizerPIITransform.setup()`
3. Add context indicators to `config/config_*.json`
4. Add detection score threshold to `config/redactConfig.yaml`
5. Test with DirectRunner before deploying to Dataflow

## License

Proprietary - Sky UK Limited

## Support

For issues or questions:
- **Team**: Sky UK Data Engineering
- **Repository**: [Link to repo]
- **Documentation**: This README

---

**Last Updated**: 2024-01-XX  
**Version**: 1.0.0  
**Apache Beam**: 2.61.0  
**Python**: 3.9  
**Presidio**: 2.2.359
