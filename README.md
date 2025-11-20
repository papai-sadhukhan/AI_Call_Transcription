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

### Environment Configs

**`config/config_dev.json`** - Development environment (100 record limit)
**`config/config_prod.json`** - Production environment (full dataset)

**Key Configuration Options:**
- `project`: GCP project settings, service accounts, region, staging locations
- `dataset`: Input/output BigQuery datasets
- `tables`: Source/target table names and column mappings
- `processing`: Record limits, batch sizes, filter conditions
- `pii_entities`: Entity type to redaction placeholder mappings
- `context_indicators`: Keywords that trigger context-aware detection for each entity type

### PII Detection Config

**`config/redactConfig.yaml`** - PII detection rules and model configuration

**Main Sections:**
- `nlp_engine_name` & `models`: spaCy NLP model configuration (en_core_web_lg)
- `ner_model_configuration`: Entity mappings from spaCy NER to Presidio entities
- `deny_list`: 179+ conversational words to prevent false positives
- `number_words`: Spoken number words (ZERO through HUNDRED, plus OH, DOUBLE, TRIPLE)
- `filler_words`: Common filler words to skip during extraction
- `name_boundaries`: Words that typically follow names in introductions
- `validation`: Person entity validation settings (conversational ratio threshold)
- `detection_scores`: Minimum confidence threshold for detections

## PII Detection Logic

### Detection Strategy: **Context-Based (Stateful)**
All custom recognizers analyze conversation context to determine what type of PII is expected in the current response. This approach provides:
- **Higher Accuracy**: Recognizes PII based on conversation flow
- **Fewer False Positives**: Only looks for specific entities when contextually appropriate
- **Better Handling of Spoken Format**: Designed for transcribed conversations with number words
- **Simplified Logic**: Simple pattern matching when context is clear (address, postcode)

### Architecture

```
ConversationContextTracker
    ↓ (tracks conversation state)
    ↓
Custom Recognizers (9 stateful recognizers)
    ↓ (detect context-specific PII)
    ↓
SpacyRecognizer (default NER for names)
    ↓ (provides broad name detection)
    ↓
Deny List Filter (179 conversational words)
    ↓ (removes false positives)
    ↓
Anonymizer Engine
    ↓ (replaces detected PII)
    ↓
Redacted Output
```

### Entity Detection Methods

#### **1. REFERENCE_NUMBER**
**Recognizer:** `StatefulReferenceNumberRecognizer`
**Entity Type:** `REFERENCE_NUMBER`
**Replacement:** `[REDACTED REFERENCE]`

**Detection Logic:**
```python
Context Required: Previous turn contains keywords like:
  - "REFERENCE NUMBER", "REF NUMBER", "REFERENCE CODE"
  - "BOOKING NUMBER", "ORDER NUMBER"

Detection Pattern:
  → Scan for sequences of 8+ consecutive number words or digits
  → Example: "ONE NINE ONE TWO ONE TWO EIGHT NINE"
  → Score: 0.95

Edge Cases Handled:
  - Mixed format: "19121289" or "ONE NINE 12 12 89"
  - With separators: "ONE NINE DASH ONE TWO"
```

**Example:**
```
Agent: "CAN I HAVE YOUR REFERENCE NUMBER PLEASE"
Customer: "YES IT'S ONE NINE ONE TWO ONE TWO EIGHT NINE"
Result: "YES IT'S [REDACTED REFERENCE]"
```

---

#### **2. BANK_DIGITS** (Last 2 digits of account)
**Recognizer:** `StatefulBankDigitsRecognizer`
**Entity Type:** `BANK_DIGITS`
**Replacement:** `[REDACTED ACCOUNT]`

**Detection Logic:**
```python
Context Required: Previous turn contains keywords like:
  - "LAST TWO DIGIT", "FINAL 2 DIGIT"
  - "LAST 2 NUMBER", "ENDING IN"
  - "ACCOUNT NUMBER" + "LAST"

Detection Pattern:
  → Find exactly 2 consecutive number words or digits
  → Example: "FIVE SIX"
  → Score: 0.95

Edge Cases Handled:
  - Digit format: "56"
  - Mixed: "FIVE 6"
  - With filler words: "UM FIVE SIX" → extracts just "56"
```

**Example:**
```
Agent: "WHAT ARE THE LAST TWO DIGITS OF YOUR ACCOUNT"
Customer: "FIVE SIX"
Result: "[REDACTED ACCOUNT]"
```

---

#### **3. CARD_DIGITS** (Last 4 digits of card)
**Recognizer:** `StatefulCardDigitsRecognizer`
**Entity Type:** `CARD_DIGITS`
**Replacement:** `[REDACTED CARD]`

**Detection Logic:**
```python
Context Required: Previous turn contains keywords like:
  - "CARD NUMBER", "DEBIT CARD", "CREDIT CARD"
  - "LAST 4 DIGIT", "ENDING"

Detection Pattern:
  → Find exactly 4 consecutive number words or digits
  → Example: "ONE TWO THREE FOUR"
  → Score: 0.95

Edge Cases Handled:
  - Same as BANK_DIGITS but with card-specific context
  - Distinguishes from bank account by keywords
```

**Example:**
```
Agent: "CAN I TAKE THE LAST FOUR DIGITS OF YOUR CARD"
Customer: "ONE TWO THREE FOUR"
Result: "[REDACTED CARD]"
```

---

#### **4. PERSON (Names)**
**Recognizers:** `StatefulNameRecognizer` (Custom) + `SpacyRecognizer` (Default NER)
**Entity Type:** `PERSON`
**Replacement:** `[REDACTED NAME]`

**Detection Logic:**
```python
StatefulNameRecognizer - Context-based patterns:

Pattern 1: Spelled Names (3+ single letters)
  → "G R A C E" → detected as name
  → Score: 0.95
  → Requires context: expecting_name=True

Pattern 2: Spelled in context
  → "MY NAME IS J O H N" → detects "J O H N"
  → Looks for intro keywords + spelled letters
  → Score: 0.95

Pattern 3: Name after keywords
  → "MY NAME IS ROSEMARY" → detects "ROSEMARY"
  → "I'M CALLED ADRIAN" → detects "ADRIAN"
  → Keywords: NAME IS, CALLED, SURNAME IS
  → Score: 0.92

Pattern 4: Agent self-introduction (UNCONDITIONAL)
  → "MY NAME IS SHAUNA" → detects "SHAUNA"
  → Works WITHOUT expecting_name context
  → Specific pattern: "MY NAME IS/MY NAME'S [NAME]"
  → Score: 0.98
  → Note: Simplified to avoid false positives

Pattern 5: Direct name response (DISABLED)
  → Previous implementation caused false positives
  → Matched common words like DOING, FINE, TRYING
  → Now disabled - relies on SpacyRecognizer instead

SpacyRecognizer - Broad NER detection:
  → Uses spaCy en_core_web_lg model
  → Detects PERSON entities in natural language
  → Filtered by deny_list validation (see below)
  → Score: varies based on spaCy confidence

Validation & Filtering:
  → deny_list: 179 conversational words
  → For PERSON entities NOT from StatefulNameRecognizer:
    - Calculate: conversational_ratio = (words in deny_list) / (total words)
    - If ratio > 50% → filtered out (false positive)
  → Examples filtered: "DOING", "FINE", "TALKING", "MY TABLET"
```

**Examples:**
```
Agent: "CAN I HAVE YOUR FULL NAME"
Customer: "IT'S ADRIAN BEESTON"
Result: "IT'S [REDACTED NAME]"

Agent: "HOW DO YOU SPELL THAT"
Customer: "A D R I A N"
Result: "[REDACTED NAME]"

Agent: "THANK YOU FOR CALLING MY NAME IS SHAUNA"
Result: "THANK YOU FOR CALLING MY NAME IS [REDACTED NAME]"
```

---

#### **5. LOCATION (Address)**
**Recognizer:** `StatefulAddressRecognizer`
**Entity Type:** `LOCATION`
**Replacement:** `[REDACTED LOCATION]`

**Detection Logic:**
```python
SIMPLIFIED APPROACH:
1. Check if agent asked for address (context keywords: ADDRESS, STREET, POSTCODE, etc.)
2. If yes, redact ANY alphanumeric content in the response
3. Skip only common filler words (YES, SO, IT, IT'S, IS, THE, MY, AND, A, AN)

Strategy:
  → When context expects address, look for ANY significant content
  → Extract: alphanumeric words, single letters, number words
  → If response has 2+ significant elements → redact as address
  → Redacts from first to last significant word
  → Score: 0.95

Why Simple Works:
  → Addresses are alphanumeric by nature
  → After agent asks "what's your address", customer's response IS the address
  → No need for complex pattern matching
  → Handles mixed formats: "C FOUR SIX WEDNESDAY BILL"
```

**Examples:**
```
Agent: "WHAT'S YOUR ADDRESS"
Customer: "IT'S TWO MILTON DRIVE"
Result: "IT'S [REDACTED LOCATION]"

Agent: "CAN I HAVE YOUR FULL NAME AND ADDRESS"
Customer: "YES SO IT'S BETTER C FOUR SIX WEDNESDAY BILL"
Result: "YES SO IT'S [REDACTED LOCATION]"
(Note: Entire alphanumeric sequence including name is redacted)
```

---

#### **6. UK_POSTCODE**
**Recognizer:** `StatefulPostcodeRecognizer`
**Entity Type:** `UK_POSTCODE`
**Replacement:** `[REDACTED POSTCODE]`

**Detection Logic:**
```python
SIMPLIFIED APPROACH:
1. Check if agent asked for postcode (context keywords: POSTCODE, POST CODE, etc.)
2. If yes, redact ANY letters + numbers in the response
3. Skip only common filler words (YES, SO, IT, IT'S, IS, THE, MY, AND, A, AN)

Strategy:
  → When context expects postcode, look for mix of letters and numbers
  → Extract: letters (especially short ones), number words, digits
  → If response has letters AND numbers → redact as postcode
  → Minimum 2 significant elements required
  → Redacts from first to last significant element
  → Score: 0.95

Why Simple Works:
  → UK postcodes always contain both letters and numbers
  → After agent asks "what's your postcode", customer's response IS the postcode
  → No need to validate postcode format
  → Handles spoken format: "HD TWO FIVE C F" or "ER SEVEN SIX Q T"

Example Detection:
  "HD TWO FIVE C F"
  → Letters: [HD, C, F]
  → Numbers: [TWO, FIVE]
  → Both present → postcode detected
```

**Examples:**
```
Agent: "WHAT'S YOUR POSTCODE"
Customer: "IT'S ER SEVEN SIX Q T"
Result: "IT'S [REDACTED POSTCODE]"

Agent: "AND YOUR POSTCODE"
Customer: "HD TWO FIVE C F"
Result: "[REDACTED POSTCODE]"
```

---

#### **7. EMAIL_ADDRESS**
**Recognizer:** `StatefulEmailRecognizer`
**Entity Type:** `EMAIL_ADDRESS`
**Replacement:** `[REDACTED EMAIL]`

**Detection Logic:**
```python
Context Required: Previous turn contains keywords like:
  - "EMAIL", "E MAIL", "EMAIL ADDRESS"

Detection Patterns:

Pattern 1: Standard email format
  → Contains: @ and DOT/. in domain
  → Example: "john@example.com"
  → Regex: [A-Z]+@[A-Z]+\\.+
  → Score: 0.95

Pattern 2: Spoken email (AT and DOT)
  → Example: "JOHN AT EXAMPLE DOT COM"
  → Example: "ADRIAN BEESTON THIRTEEN AT GMAIL DOT COM"
  → Score: 0.95

Note: Common spoken patterns in transcripts
```

**Example:**
```
Agent: "WHAT'S YOUR EMAIL ADDRESS"
Customer: "IT'S ADRIAN BEESTON THIRTEEN AT GMAIL DOT COM"
Result: "IT'S [REDACTED EMAIL]"
```

---

#### **8. PASSWORD**
**Recognizer:** `StatefulPasswordRecognizer`
**Entity Type:** `PASSWORD`
**Replacement:** `[REDACTED PASSWORD]`

**Detection Logic:**
```python
Context Required: Previous turn contains keywords like:
  - "PASSWORD", "PASSCODE", "PIN"
  - "SECURITY", "ACCESS CODE"

Detection Strategy:
  → Passwords are sequences of letters and numbers
  → Look for consecutive:
    - Single letters (A, B, C)
    - Number words (ONE, TWO, THREE)
    - Digits (1, 2, 3)
  
  → Filter out conversational words from deny_list
  → Minimum sequence length: 2 elements (updated from 6)
  → Score: 0.95
  → Handles short passwords like "O B", "A 1", etc.

Smart Parsing:
  → Preserves conversational prefix/suffix
  → Only redacts the password sequence itself
  → Example: "IT IS WRITTEN DOWN HERE SOMEWHERE [PASSWORD]"
              → "IT IS WRITTEN DOWN HERE SOMEWHERE [REDACTED PASSWORD]"

Edge Cases:
  → Handles mixed format: "A B C ONE TWO 3"
  → Ignores filler words: "UM", "UH", "LIKE"
  → Stops at conversational phrases
```

**Examples:**
```
Agent: "CAN YOU PROVIDE YOUR PASSWORD"
Customer: "IT IS WRITTEN DOWN SOMEWHERE THREE THREE TWO C D C Q I J SEVEN SIX EIGHT E"
Result: "IT IS WRITTEN DOWN SOMEWHERE [REDACTED PASSWORD]"

Agent: "WHAT'S YOUR PASSWORD"
Customer: "O B"
Result: "[REDACTED PASSWORD]"
(Note: Short passwords now supported with 2-character minimum)
```

---

#### **9. PHONE_NUMBER** ✨ NEW
**Recognizer:** `StatefulPhoneNumberRecognizer`
**Entity Type:** `PHONE_NUMBER`
**Replacement:** `[REDACTED PHONE]`

**Detection Logic:**
```python
Simple Pattern Matching - NO context required
  → Detects sequences of 9+ consecutive number words
  → Number words: ZERO, ONE, TWO, THREE, FOUR, FIVE, SIX, SEVEN, EIGHT, NINE
  → Special words: OH (=0), DOUBLE (XX), TRIPLE (XXX)

Detection Patterns:

Pattern 1: Spoken phone numbers
  → Example: "ZERO DOUBLE SEVEN NINE FOUR FIVE OH FIVE EIGHT THREE SIX"
  → Detects: 9+ consecutive number words
  → Score: 0.95

Pattern 2: Digit sequences
  → Example: "07945058361"
  → Detects: 10-11 consecutive digits starting with 0
  → Score: 0.90

Why Simple Pattern Works:
  → Phone numbers are distinctive: 10-11 consecutive numbers
  → Rarely occurs in normal conversation
  → "DOUBLE" is unique to phone number context
  → No false positives found in testing

Note: This recognizer is UNCONDITIONAL
  → Works without context indicators
  → Always active throughout conversation
```

**Examples:**
```
Agent: "CAN I HAVE YOUR MOBILE NUMBER"
Customer: "IS ZERO DOUBLE SEVEN NINE FOUR FIVE OH FIVE EIGHT THREE SIX"
Result: "IS [REDACTED PHONE]"

Customer: "MY NUMBER IS 07945058361"
Result: "MY NUMBER IS [REDACTED PHONE]"
```

---

### False Positive Prevention

**Multi-Layer Filtering Strategy:**

#### **1. Deny List (redactConfig.yaml)**
- **179 conversational words** organized by category:
  - Modal verbs: CAN, COULD, SHOULD, WOULD, WILL, etc.
  - Adverbs: JUST, VERY, REALLY, QUITE, ALWAYS, etc.
  - Common words: THAT, THIS, WITH, FROM, LIKE, etc.
  - Device names: TABLET, PHONE, DEVICE, LAPTOP, etc. (prevent "MY TABLET" → PERSON)

#### **2. Dual-Purpose Filtering**

**Exact Match Filter (main.py):**
```python
# Applied to ALL entities
if matched_text in deny_list:
    skip_detection()

# Word-level check (for multi-word detections)
if any(word in deny_list for word in matched_text.split()):
    skip_detection()

# Exception: Structured entities bypass this filter
# (PHONE_NUMBER, EMAIL_ADDRESS, CREDIT_CARD, IBAN_CODE)
```

**Validation Filter (for PERSON entities):**
```python
# Only for PERSON entities from SpacyRecognizer
if entity_type == "PERSON" and not from_custom_recognizer:
    words = matched_text.split()
    conversational_words = [w for w in words if w in deny_list]
    ratio = len(conversational_words) / len(words)
    
    if ratio > 0.5:  # More than 50% conversational
        reject_as_false_positive()
```

#### **3. Context-Based Activation**
- Most recognizers only activate when context indicates PII is expected
- Reduces search space and false positive rate
- Example: BANK_DIGITS only looks for 2 digits when agent asks for "last two digits"

#### **4. Pattern Specificity**
- Patterns designed to match PII structure, not general text
- Example: UK_POSTCODE requires mix of letters AND numbers
- Example: PASSWORD requires 2+ consecutive alphanumeric characters

**False Positive Examples (Prevented):**
```
❌ "DOING" detected as PERSON → Filtered (100% conversational)
❌ "MY TABLET" detected as PERSON → Filtered (TABLET in deny_list)
❌ "I AM FINE" detected as PERSON → Filtered (all words conversational)
❌ "YOU'RE" detected as PERSON → Filtered (contraction in deny_list)
✅ "ADRIAN" detected as PERSON → Kept (real name, context expecting name)
✅ "SHAUNA" in "MY NAME IS SHAUNA" → Kept (agent intro pattern)
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
