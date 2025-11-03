# Codebase Deep Dive Analysis

## Executive Summary

This codebase implements a **PII (Personally Identifiable Information) redaction pipeline** for Sky customer service call transcripts using Apache Beam, Microsoft Presidio, and Google Cloud Platform services. The system processes conversation transcripts stored in BigQuery, identifies sensitive information, and redacts it with placeholder characters (`#####`).

---

## Architecture Overview

### High-Level Flow
```
BigQuery (Input) 
    ↓
Apache Beam Pipeline
    ↓
JSON Parsing (Conversation Transcript)
    ↓
Text Preprocessing (spoken_to_numeric)
    ↓
PII Analysis (Presidio Analyzer + Custom Recognizers)
    ↓
PII Redaction (Presidio Anonymizer)
    ↓
BigQuery (Output)
```

### Technology Stack
- **Pipeline Framework**: Apache Beam 2.66.0
- **PII Detection**: Microsoft Presidio (Analyzer 2.2.359, Anonymizer 2.2.359)
- **NLP Engine**: spaCy 3.8.7 with `en_core_web_lg` model
- **Cloud Platform**: Google Cloud Platform (BigQuery, Dataflow)
- **Language**: Python 3.x

---

## Core Components

### 1. **main.py** - Pipeline Orchestration

#### Purpose
Main entry point for the PII redaction pipeline. Orchestrates data flow from BigQuery input to redacted BigQuery output.

#### Key Classes & Functions

##### `load_config(config_path)`
- Loads JSON configuration file containing project settings, table mappings, and PII entity definitions
- Returns configuration dictionary

##### `deconstruct_transcript(conversation_transcript: list) -> str`
- Converts structured conversation transcript (list of role/content dicts) into flat string
- Used for creating the `redacted_transcript` field
- **Format**: Concatenates all content fields with spaces

##### `DirectPIITransform(beam.DoFn)`
**Purpose**: Core transformation class that performs PII detection and redaction on each conversation turn.

**Initialization** (`__init__`):
- Stores configuration
- Initializes analyzer, anonymizer, and operator placeholders

**Setup** (`setup`):
- Lazy initialization of Presidio components (important for Beam worker distribution)
- Loads `redactConfig.yaml` for NLP engine configuration
- Registers custom recognizers:
  - `SpokenAddressRecognizer`
  - `VerificationCodeRecognizer`
  - `BankLastDigitsRecognizer`
  - `SpokenPostcodeRecognizer`
  - `SpelledOutNameRecognizer`
- Builds operator config for each PII entity type

**Process** (`process`):
- Iterates through each conversation turn (role + content)
- **Preprocessing**: Applies `spoken_to_numeric()` to convert spoken numbers to digits
- **Analysis**: Presidio analyzer detects entities
- **Filtering**: Only keeps entities with score > 0.7
- **Redaction**: Replaces detected PII with `#####` or configured replacement
- **Output**: Returns element with:
  - `conversation_transcript`: Redacted conversation structure
  - `redacted_transcript`: Flattened redacted text
  - `redacted_entity`: Semicolon-separated list of matched entities with metadata

##### `run(argv=None)`
Main pipeline execution function:
1. Parses command-line arguments (`--config_path`, `--runner`)
2. Loads configuration
3. Sets up Beam pipeline options (Dataflow or DirectRunner)
4. Constructs BigQuery input query
5. Defines transformation pipeline:
   - Read from BigQuery
   - Parse conversation JSON
   - Apply PII redaction
   - Prepare output format
   - Write to BigQuery
6. Handles both streaming inserts and batch writes

---

### 2. **redactConfig.yaml** - NLP Configuration

#### Purpose
Configures the spaCy NLP engine and entity mapping for Presidio.

#### Key Sections

##### NLP Engine Configuration
```yaml
nlp_engine_name: spacy
models:
  - lang_code: en
    model_name: en_core_web_lg
```

##### Entity Mapping
Maps spaCy NER labels to Presidio entity types:
- **Person Entities**: PER, PERSON, HCW → PERSON
- **Contact**: EMAIL → EMAIL, PHONE → PHONE_NUMBER
- **Location**: FAC, GPE, LOC → LOCATION
- **Address**: ADDRESS, STREET_ADDRESS, HOUSE_NUMBER, POSTCODE
- **Credentials**: PASSWORD, VERIFICATION_CODE
- **Other**: AGE

##### Low Confidence Handling
```yaml
low_confidence_score_multiplier: 0.4
```
Reduces scores for uncertain entities.

##### Ignored Labels
Filters out non-PII entities to reduce false positives:
- CARDINAL, EVENT, LANGUAGE, LAW, ORDINAL, PERCENT, PRODUCT, QUANTITY, WORK_OF_ART, NUMBERS, NUMBER

---

### 3. **utils/spoken_to_numeric.py** - Text Preprocessing

#### Purpose
Converts spoken/written numbers to numeric format while preserving context.

#### `spoken_to_numeric(text: str) -> str`

**Functionality**:
1. **Protects Ordinals**: Masks ordinal words (first, second, third, etc.) to prevent conversion
2. **Protects Unit Phrases**: Masks phrases like "two minutes", "five pounds" to preserve natural language
3. **Converts Cardinals**: Uses `text2digits` library to convert "thirty" → "30", "two hundred" → "200"
4. **Restores Protected Text**: Unmasks previously protected ordinals and units
5. **Merges Single Letters**: Joins sequences like "C F" → "CF" for spelled-out codes

**Example Transformations**:
- "THIRTY YEARS" → "30 YEARS"
- "TWO ONE FIVE" → "215"
- "C A P I T A L X" → "CAPITAL X" (single letters joined when appropriate)
- "FIRST TIME" → "FIRST TIME" (ordinal preserved)

---

### 4. **utils/customer_registry.py** - Custom PII Recognizers

#### Purpose
Implements domain-specific PII recognizers for scenarios not covered by standard Presidio.

#### Custom Recognizers

##### `SpelledOutNameRecognizer`
- **Entity**: PERSON
- **Pattern**: Detects names spelled letter-by-letter (e.g., "J U N E P A Y N E")
- **Method**: 
  - Joins single-letter tokens
  - Uses regex for capitalized word sequences
  - Requires contextual keywords: "name", "called", "surname", etc.
- **Score**: 0.9 when context matched

##### `SpokenPostcodeRecognizer`
- **Entity**: UK_POSTCODE
- **Pattern**: UK postcode format (e.g., "B77 5AS" or spoken "BRAVO 775 ALPHA SIERRA")
- **Method**:
  - Direct regex matching
  - NATO phonetic alphabet decoding
  - Contextual validation with keywords: "postcode", "address", "code", "location"
- **Score**: 0.9 for direct match, 0.95 for phonetic + context

##### `SpokenAddressRecognizer`
- **Entity**: ADDRESS
- **Pattern**: Street addresses with numbers and street types
- **Regex**: `\b\d{1,5}\s+(?:street|road|lane|avenue|drive|close|way|place|...)\b`
- **Method**:
  - Normalizes spoken digits (O/OH → 0, TWO/TO → 2)
  - Context keywords: "address", "flat", "house", "road", "street", "avenue"
  - NLP fallback: Checks for nearby location entities (GPE, LOC, FACILITY)
- **Score**: 0.4 base, boosted to 0.85 with context

##### `VerificationCodeRecognizer`
- **Entity**: VERIFICATION_CODE
- **Pattern**: 4-6 digit sequences
- **Regex**: `\b\d{4,6}\b`
- **Method**: Context-dependent (requires nearby keywords: "verification", "otp", "code", "security", "pin", "auth")
- **Score**: 0.3 base, boosted by context

##### `BankLastDigitsRecognizer`
- **Entity**: BANK_ACCOUNT_LAST_DIGITS
- **Pattern**: 2-digit sequences
- **Regex**: `\b\d{2}\b`
- **Method**: 
  - Very low base score (0.1)
  - Requires strong context: "bank", "account", "digits", "ending", "sort code"
  - Filters out date-like patterns (month names, ordinal suffixes)
- **Score**: 0.1 base, context required

---

## Configuration Structure

### config_dev.json / config_prod.json

#### Project Configuration
```json
{
  "project": {
    "bigquery_project_id": "project-for-data-source",
    "dataflow_project_id": "project-for-runner",
    "region": "europe-west1",
    "staging_location": "gs://bucket/staging",
    "temp_bigquery_dataset": "dataflow_temp_dataset",
    "job_name": "call-transcript-redaction-job"
  }
}
```

#### Dataset & Tables
```json
{
  "dataset": {
    "input": "uk_call_transcript_exprmnt",
    "output": "uk_call_transcript_exprmnt"
  },
  "tables": {
    "source": {
      "name": "td_call_redaction_p1",
      "columns": {
        "transaction_id": "transaction_id",
        "transcription_file_dt": "file_date",
        "input_transcript": "transcription"
      }
    },
    "target": {
      "name": "td_call_redaction_p2",
      "columns": {
        "file_date": "file_date",
        "transaction_id": "transaction_id",
        "transcription_redacted": "transcription_redacted",
        "redacted_entity": "redacted_entity",
        "load_dt": "load_dt"
      }
    }
  }
}
```

#### PII Entity Replacements
```json
{
  "pii_entities": {
    "PERSON": "#####",
    "AGE": "#####",
    "EMAIL_ADDRESS": "#####",
    "PHONE_NUMBER": "#####",
    "LOCATION": "#####",
    "POSTAL_CODE": "#####",
    "ADDRESS": "#####",
    "PASSWORD": "#####",
    "VERIFICATION_CODE": "#####"
  }
}
```

#### Processing Parameters
```json
{
  "processing": {
    "limit": 1000,
    "batch_size": 3000,
    "selected_fields": ["transaction_id", "file_date", "transcription"],
    "condition": "1=1"
  }
}
```

---

## Data Flow & Transformations

### Input Format
```json
{
  "transaction_id": "TXN123",
  "file_date": "2025-01-01",
  "transcription": "[{\"role\":\"Agent\",\"content\":\"HELLO MY NAME IS JOHN\"},{\"role\":\"Customer\",\"content\":\"HI THERE\"}]"
}
```

### Transformation Steps

1. **Parse JSON**: Convert transcription string to list of dicts
2. **For Each Turn**:
   - Extract content
   - Apply `spoken_to_numeric()` conversion
   - Analyze with Presidio + custom recognizers
   - Filter entities by score > 0.7
   - Redact PII
3. **Reconstruct**: Build redacted conversation structure
4. **Output Preparation**: Create output row with redacted transcript

### Output Format
```json
{
  "file_date": "2025-01-01",
  "transaction_id": "TXN123",
  "transcription_redacted": "[{\"role\":\"Agent\",\"content\":\"HELLO MY NAME IS #####\"},{\"role\":\"Customer\",\"content\":\"HI THERE\"}]",
  "redacted_entity": "Matched entity: PERSON, text: JOHN, score: 0.95",
  "load_dt": "2025-11-03T12:00:00.000000"
}
```

---

## Issues Identified

### Issue #1: False Positive on "YOU'RE"

**Problem**:
```
Original: "YOU'RE WELCOME BYE HAVE A NICE DAY"
Current Output: "##### WELCOME BYE HAVE A NICE DAY"
Expected: "YOU'RE WELCOME BYE HAVE A NICE DAY"
Matched entity: PERSON, text: YOU'RE, score: 0.85
```

**Root Cause**:
- spaCy's NER model (`en_core_web_lg`) incorrectly classifies "YOU'RE" as a PERSON entity
- This is a known issue with contractions at sentence start or in all-caps text
- The score 0.85 exceeds the threshold of 0.7, so it gets redacted

**Why This Happens**:
- spaCy models trained on mixed-case text struggle with all-caps
- Contractions ("YOU'RE", "I'M", "WE'RE") can be misclassified as names in certain contexts
- No contextual validation to verify if "YOU'RE" is actually a person name

### Issue #2: Missing Verification Code Redaction

**Problem**:
```
Original: "CAPITAL X J L TWO ONE FIVE M E"
After spoken_to_numeric: "CAPITAL X J L 215 M E"
Current Output: "CAPITAL X J L 215 M E" (not redacted)
Expected: "CAPITAL #####"
```

**Root Cause**:
- The `VerificationCodeRecognizer` only matches pure 4-6 digit sequences (`\b\d{4,6}\b`)
- After conversion, "X J L 215 M E" becomes "X J L 215 M E" with letters mixed in
- The pattern doesn't match because letters are present
- Alphanumeric verification codes/passwords are not detected

**Why This Happens**:
- Recognizer expects clean numeric codes
- Mixed alphanumeric patterns (common in passwords/verification codes) are not covered
- No recognizer for spelled-out alphanumeric sequences

---

## Generalization Needs

### Current Limitations

1. **Hard-coded Patterns**: Many recognizers use fixed regex patterns that don't adapt to variations
2. **Context Dependency**: Over-reliance on exact keyword matches
3. **All-Caps Bias**: System designed for transcribed speech (all caps) but struggles with NER accuracy
4. **Limited Alphanumeric Support**: Verification codes mixing letters and numbers aren't detected
5. **No False Positive Filtering**: No post-processing to eliminate common false positives (pronouns, common words)

### Recommended Improvements

1. **Pre-processing Normalization**:
   - Convert all-caps to sentence case before NER analysis
   - Restore original casing after redaction

2. **Pronoun/Common Word Filter**:
   - Blacklist common false positives: YOU'RE, I'M, WE'RE, THEY'RE, HE'S, SHE'S
   - Check against dictionary of pronouns and common contractions

3. **Enhanced Alphanumeric Code Detection**:
   - Pattern for mixed letter-digit sequences: `[A-Z0-9\s]{5,20}`
   - Context: "password", "code", "verification", "written down"
   - Detect spelled-out codes: "CAPITAL X J L 215"

4. **Context Window Analysis**:
   - Analyze surrounding sentence structure
   - Use grammatical roles (subject, object) to validate entities
   - Leverage spaCy's dependency parsing

5. **Score Calibration**:
   - Increase threshold for PERSON entities to 0.9
   - Lower threshold for PASSWORD/VERIFICATION_CODE to 0.6 when context is strong

6. **Multi-pass Processing**:
   - Pass 1: Detect high-confidence entities (names, addresses)
   - Pass 2: Detect contextual entities (codes, passwords)
   - Pass 3: Filter false positives

---

## Testing Strategy

### Current Test Setup
- **Test Input**: `test/input.txt` - Sample conversation transcript
- **Test Output**: `test/output.txt` - Expected redacted output
- **Inspector**: `test/inspect_entity.py` - spaCy entity visualization tool

### Recommended Test Cases

1. **Pronouns & Contractions**: YOU'RE, I'M, WE'RE, THEY'RE, IT'S, THAT'S
2. **Alphanumeric Codes**: "CAPITAL X J L 215 M E", "ABC123", "12XYZ34"
3. **Context Variations**: Different ways customers say "password", "verification code"
4. **Edge Cases**: Single letters, numbers in different contexts
5. **Real Conversations**: Full call transcripts with multiple PII types

---

## Performance Considerations

### Current Performance
- **Processing**: ~1000 records per batch (configurable)
- **Batch Size**: 3000 for BigQuery writes
- **Runner**: DataflowRunner for production, DirectRunner for testing

### Optimization Opportunities
1. **Caching**: Cache NLP model and analyzer in worker setup
2. **Batch Processing**: Group turns from same conversation for single NLP pass
3. **Lazy Loading**: Current `setup()` method already implements lazy loading ✓
4. **Parallel Processing**: Beam's ParDo already enables parallelization ✓

---

## Security & Compliance

### PII Categories Covered
- ✅ Personal Names (PERSON)
- ✅ Contact Info (EMAIL, PHONE)
- ✅ Locations (ADDRESS, POSTCODE)
- ✅ Financial (BANK_ACCOUNT_LAST_DIGITS)
- ✅ Credentials (PASSWORD, VERIFICATION_CODE)
- ✅ Age

### Audit Trail
- Each redacted entity logged with:
  - Entity type
  - Matched text
  - Confidence score
- Stored in `redacted_entity` column for compliance review

---

## Deployment

### Local Development
```bash
python main.py --config_path config_dev.json --runner DirectRunner
```

### Production Deployment
```bash
python main.py --config_path config_prod.json --runner DataflowRunner
```

### Required Permissions
- BigQuery: `roles/bigquery.dataViewer` (source), `roles/bigquery.dataEditor` (target)
- Dataflow: `roles/dataflow.developer`
- Cloud Storage: `roles/storage.objectAdmin` (staging bucket)

---

## Conclusion

This is a well-structured PII redaction pipeline with good separation of concerns. The main issues stem from:
1. **NER model limitations** with all-caps text and contractions
2. **Pattern rigidity** not covering all alphanumeric code variations

The recommended fixes will make the system more robust and generalizable while maintaining performance and accuracy.
