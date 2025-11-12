# Local Development Guide

## Usage Examples


### Run with BigQuery (dev/prod config)
You must now specify the config file using `--config_path`:

**For development:**
```bash
python main.py --config_path config_dev.json --runner DataflowRunner
```

**For production:**
```bash
python main.py --config_path config_prod.json --runner DataflowRunner
```

The pipeline reads from the configured BigQuery table in the selected config file.

## Overview
This folder contains the PII redaction pipeline configured for local development and testing. It's essentially the same as the main production pipeline but with updated table names and the ability to run locally using DirectRunner.

## Quick Start

Install latest Presidio:
pip install --upgrade git+https://github.com/microsoft/presidio.git#subdirectory=presidio-analyzer
pip install --upgrade git+https://github.com/microsoft/presidio.git#subdirectory=presidio-anonymizer


### 1. Setup Environment
```bash
# Navigate to the local_run directory
cd local_run

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_lg
```


### 2. Run Local Pipeline
```bash
python main.py --config_path config_dev.json --runner DirectRunner
```
Run Local Pipeline - Prod
```bash
python main.py --config_path config_prod.json --runner DirectRunner
```
## What's Different from Production

| Production (Parent Directory) | Local Development (This Folder) |
|-------------------------------|----------------------------------|
| **Tables**: Original production tables | **Tables**: Experiment tables (td_verint_transcription_raw → td_verint_transcription_redacted_temp) |
| **Project**: skyuk-uk-customer-tds-dev | **Project**: skyuk-uk-reg-expmnt-prod |
| **Default Runner**: DataflowRunner | **Flexible Runner**: DirectRunner (local) or DataflowRunner (cloud) |
| **Usage**: Fixed configuration | **Usage**: Command-line configurable |

## Files in This Directory

### `main.py`
- **Purpose**: Configurable pipeline for conversation transcript redaction
- **Key Features**:
  - Configuration-driven (uses `config.json`)
  - Handles conversation transcript format with role/content structure
  - Command-line runner selection (DirectRunner/DataflowRunner)
  - Same PII detection logic as production
  - Flexible table and column mapping

### `config.json`
- **Purpose**: Central configuration file for all pipeline settings
- **Contains**:
  - Project and dataset configurations
  - Table names and column mappings
  - PII entity replacement rules
  - Processing parameters (limits, batch sizes)
  - Dataflow execution settings

### `requirements.txt`
- **Purpose**: All dependencies needed for local development
- **Includes**:
  - Apache Beam
  - Presidio libraries
  - spaCy
  - Development tools

### `README.md`
- **Purpose**: This documentation file

## PII Detection Logic

### Recent Improvements (Nov 2024)

**Simplified Address & Postcode Recognition:**
- **Problem Solved**: Previous complex patterns failed on mixed responses like "BETTER C FOUR SIX WEDNESDAY BILL HD TWO FIVE C F" (name + address + postcode in one response)
- **New Approach**: Context-based detection with simple pattern matching
  - When agent asks for address/postcode → redact ANY alphanumeric content
  - No complex pattern validation needed
  - Handles spoken numbers and letters naturally
- **Benefits**: 
  - Works with mixed responses (name+address+postcode together)
  - Handles any spoken format (letters, numbers, words)
  - Much simpler logic = fewer edge cases = more reliable

**Short Password Support:**
- **Updated**: Minimum password length reduced from 6 to 2 characters
- **Reason**: Support short passwords like "O B", "A 1", etc.
- **Impact**: Now detects and redacts all password formats including very short ones

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

#### **2. BANK_DIGITS** (Last 4 digits of account)
**Recognizer:** `StatefulBankDigitsRecognizer`  
**Entity Type:** `BANK_DIGITS`  
**Replacement:** `[REDACTED ACCOUNT]`

**Detection Logic:**
```python
Context Required: Previous turn contains keywords like:
  - "LAST FOUR DIGIT", "FINAL 4 DIGIT"
  - "LAST 4 NUMBER", "ENDING IN"
  - "ACCOUNT NUMBER" + "LAST"

Detection Pattern:
  → Find exactly 4 consecutive number words or digits
  → Example: "FIVE SIX SEVEN EIGHT"
  → Score: 0.95

Edge Cases Handled:
  - Digit format: "5678"
  - Mixed: "FIVE SIX 7 8"
  - With filler words: "UM FIVE SIX SEVEN EIGHT" → extracts just "5678"
```

**Example:**
```
Agent: "WHAT ARE THE LAST FOUR DIGITS OF YOUR ACCOUNT"
Customer: "FIVE SIX SEVEN EIGHT"
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
- Example: BANK_DIGITS only looks for 4 digits when agent asks for "last four digits"

#### **4. Pattern Specificity**
- Patterns designed to match PII structure, not general text
- Example: UK_POSTCODE requires mix of letters AND numbers
- Example: PASSWORD requires 6+ consecutive alphanumeric characters

**False Positive Examples (Prevented):**
```
❌ "DOING" detected as PERSON → Filtered (100% conversational)
❌ "MY TABLET" detected as PERSON → Filtered (TABLET in deny_list)
❌ "I AM FINE" detected as PERSON → Filtered (all words conversational)
❌ "YOU'RE" detected as PERSON → Filtered (contraction in deny_list)
✅ "ADRIAN" detected as PERSON → Kept (real name, context expecting name)
✅ "SHAUNA" in "MY NAME IS SHAUNA" → Kept (agent intro pattern)
```

### Configuration Files

**redactConfig.yaml:**
- NLP engine settings (spaCy model: en_core_web_lg)
- Entity mappings (spaCy NER → Presidio entities)
- Deny list (158 words in 10+ categories)
- Validation thresholds

**config_dev.json / config_prod.json:**
- BigQuery project/dataset/table settings
- PII entity replacement values: `[REDACTED NAME]`, `[REDACTED POSTCODE]`, etc.
- Context indicators: keywords that trigger each entity type detection
- Processing limits and batch sizes

## Configuration

All settings are now managed through `config.json`:

### Data Sources
- **Source**: Configured in `config.json` under `tables.source`
- **Target**: Configured in `config.json` under `tables.target`
- **Project**: Configurable project ID and datasets

### Table Structure

**Input Table** (`td_verint_transcription_raw`):
- `transaction_id`: Transaction identifier  
- `transcription_file_dt`: Transcript file date/time
- `conversation_transcript_json`: JSON array of conversation turns

**Output Table** (`td_verint_transcription_redacted_temp`):
- `transaction_id`: Transaction identifier (copied from input)
- `transcription_file_dt`: Transcript file date/time (copied from input)  
- `conversation_transcript_json`: JSON array with PII redacted using `#####`

### Conversation Format
The pipeline handles conversation transcripts with this structure:
```json
[
  {"role":"agent","content":"THANK YOU FOR CALLING ABC YOU'RE SPEAKING WITH AGENT_X"},
  {"role":"customer","content":"HELLO"},
  {"role":"agent","content":"YES HELLO"}
]
```

**After PII redaction:**
```json
[
  {"role":"agent","content":"THANK YOU FOR CALLING ABC YOU'RE SPEAKING WITH #####"},
  {"role":"customer","content":"HELLO"}, 
  {"role":"agent","content":"YES HELLO"}
]
```

## Usage Options


### Local Execution (DirectRunner)
```bash
python main.py --config_path config_dev.json --runner DirectRunner
```
- Runs on your local machine
- Good for testing and development
- Processes smaller datasets efficiently

### Cloud Execution (DataflowRunner)
```bash
python main.py --config_path config_prod.json --runner DataflowRunner
```
- Runs on Google Cloud Dataflow
- Scalable for large datasets
- Requires Google Cloud authentication

## Usage Examples


### Run with BigQuery
```bash
python main.py --config_path config_dev.json --runner DirectRunner
```


### Run with Local Excel File
```bash
python main.py --config_path config_dev.json --runner DirectRunner --input=Local --local_file=local_test/sample_transcript_data.xlsx --output_file=local_test/output_redacted_data.xlsx
```

- For BigQuery, the pipeline reads from the configured table in `config.json`.
- For Local, the pipeline reads from the specified Excel file and writes output to the specified Excel file.

## Customization

### Modifying Configuration
Edit `config.json` to change:


**Table Names:**
```json
{
  "tables": {
    "source": {"name": "your_source_table"},
    "target": {"name": "your_target_table"}
  }
}
```

**Column Mapping:**
```json
{
  "tables": {
    "source": {
      "columns": {
        "transaction_id": "your_id_column",
        "transcription_file_dt": "your_date_column",
        "conversation_transcript_json": "your_json_column"
      }
    }
  }
}
```

**PII Replacements:**
```json
{
  "pii_entities": {
    "PERSON": "#####",
    "PHONE_NUMBER": "#####",
    "EMAIL_ADDRESS": "#####"
  }
}
```

### Command Line Options
You can pass any Apache Beam pipeline options:
```bash
# Local execution with specific worker count
python

The pipeline uses the `redactConfig.yaml` file from the parent directory, so any changes to entity mappings or NLP settings will be reflected in local runs.

## Selecting Environment

You can now select the environment config file at runtime:

- For development: `--config_path config_dev.json`
- For production: `--config_path config_prod.json`

This allows you to switch between dev and prod settings without changing code.

## Troubleshooting

### Common Issues

#### Import Errors
```bash
# Make sure virtual environment is activated
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Reinstall dependencies
pip install -r requirements.txt
```

#### spaCy Model Missing
```bash
python -m spacy download en_core_web_lg

# Verify installation
python -c "import spacy; spacy.load('en_core_web_lg')"
```

#### Configuration File Not Found
The pipeline looks for `redactConfig.yaml` in the parent directory. Make sure you're running from the correct location:
```bash
# Should be in: .../redaction/local_run/
pwd  # or cd on Windows
ls ..  # Should show redactConfig.yaml
```

#### Memory Issues
If you encounter memory issues:
```python
# In main.py, modify pipeline options:
options = PipelineOptions([
    '--runner=DirectRunner',
    '--direct_num_workers=1',  # Reduce workers
    '--direct_running_mode=in_memory'  # Use in-memory processing
])
```

## Development Workflow

1. **Edit Code**: Make changes to `main.py`
2. **Test**: Run `python test_setup.py`
3. **Execute**: Run `python main.py`
4. **Debug**: Check console output and logs
5. **Iterate**: Repeat until satisfied

## Moving to Production

When you're ready to deploy changes to production:

1. **Update Production Code**: Apply your changes to `../main.py`
2. **Test Locally**: Run the modified production code with DirectRunner
3. **Build Containers**: Use the Cloud Build configuration
4. **Deploy**: Submit to Google Cloud Dataflow

## Performance Notes

- **Local execution** is great for development but limited by single-machine resources
- **Sample data** processes in seconds
- **Real BigQuery data** (if you run `../main.py` locally) will take longer
- **Production deployment** handles large-scale data efficiently

## Next Steps

1. Run `python test_setup.py` to verify setup
2. Run `python main.py` to see PII redaction in action
3. Experiment with the sample data and configuration
4. When ready, move to production deployment in the parent directory