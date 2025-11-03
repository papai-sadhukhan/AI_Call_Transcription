# Quick Reference Guide - PII Redaction System

## How to Add New False Positives

If you find words incorrectly being redacted as PERSON entities:

**File**: `main.py`  
**Method**: `DirectPIITransform._is_false_positive()`

```python
false_positive_words = {
    "YOU'RE", "I'M", "WE'RE",  # existing...
    "YOUR_NEW_WORD_HERE",       # ← Add here
}
```

---

## How to Add New Password Patterns

If you find password formats not being detected:

**File**: `utils/customer_registry.py`  
**Class**: `VerificationCodeRecognizer`  
**Method**: `analyze()`

```python
alphanumeric_patterns = [
    r'\b(?:CAPITAL\s+)?(?:[A-Z]\s+){2,}[A-Z0-9](?:\s+[A-Z0-9]){2,}\b',
    r'YOUR_NEW_REGEX_PATTERN_HERE',  # ← Add here
]
```

---

## How to Add Password Context Keywords

If passwords appear in new contexts:

**File**: `main.py`  
**Method**: `DirectPIITransform._detect_password_context()`

```python
password_keywords = [
    "PASSWORD", "VERIFICATION",  # existing...
    "YOUR_NEW_KEYWORD",          # ← Add here
]
```

**AND**

**File**: `utils/customer_registry.py`  
**Class**: `VerificationCodeRecognizer`

```python
password_context_keywords = [
    "password", "verification",  # existing...
    "your_new_keyword",         # ← Add here (lowercase)
]
```

---

## How to Adjust Detection Thresholds

### Increase PERSON detection threshold (reduce false positives)

**File**: `main.py`  
**Method**: `DirectPIITransform.process()`

```python
# Current: 0.7
if r.score > 0.7:  # ← Change to 0.8 or 0.9

# For specific entity types:
threshold = 0.9 if r.entity_type == "PERSON" else 0.7
if r.score > threshold:
```

### Adjust password context window

**File**: `main.py`

```python
# Current: 200 characters back
context = content[max(0, start_pos - 200):start_pos + 50]
#                                  ↑
#                          Change this value
```

---

## How to Test Changes

### Run Full Test Suite
```bash
python test_fixes.py
```

### Test Specific Issue
```python
# Edit test_fixes.py and add:
def test_my_new_case():
    original = [{"role":"Agent","content":"YOUR TEST TEXT HERE"}]
    element = {"conversation_transcript": original}
    config = {"pii_entities": {"PERSON": "#####", "PASSWORD": "#####"}}
    
    transform = DirectPIITransform(config)
    transform.setup()
    results = list(transform.process(element))
    
    print(results[0]["conversation_transcript"])
```

### Test with Real Data
```bash
# Local test with DirectRunner
python main.py --config_path config_dev.json --runner DirectRunner
```

---

## How to Debug Detection Issues

### Check what spaCy detects
```python
# Use test/inspect_entity.py
python test/inspect_entity.py "YOUR TEXT HERE"
```

### Add Debug Logging

**In `main.py`, method `process()`:**
```python
# After analyzer.analyze():
for r in analyzer_result:
    matched_text = converted_content[r.start:r.end]
    print(f"DEBUG: {r.entity_type} | {matched_text} | {r.score}")
```

**In custom recognizers:**
```python
def analyze(self, text, entities, nlp_artifacts):
    print(f"DEBUG: Analyzing text: {text[:100]}")
    results = super().analyze(text, entities, nlp_artifacts)
    print(f"DEBUG: Found {len(results)} matches")
    return results
```

---

## Common Regex Patterns

### For Alphanumeric Codes
```python
# Letters and numbers, spaces allowed
r'\b[A-Z0-9](?:\s+[A-Z0-9]){4,}\b'

# Specific format: 2 letters, 3 digits, 2 letters
r'\b[A-Z]{2}\d{3}[A-Z]{2}\b'

# Optional CAPITAL prefix
r'\b(?:CAPITAL\s+)?[A-Z0-9\s]+\b'
```

### For Phone Numbers
```python
# UK format: 020 1234 5678
r'\b0\d{2}\s?\d{4}\s?\d{4}\b'

# International: +44 20 1234 5678
r'\+\d{1,3}\s?\d{2}\s?\d{4}\s?\d{4}\b'
```

### For Email
```python
# Basic email pattern
r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
```

---

## Entity Type Reference

### Standard Entities (from Presidio)
- `PERSON` - Person names
- `EMAIL_ADDRESS` - Email addresses
- `PHONE_NUMBER` - Phone numbers
- `LOCATION` - General locations
- `AGE` - Ages

### Custom Entities (from customer_registry.py)
- `ADDRESS` - Street addresses
- `UK_POSTCODE` - UK postcodes
- `VERIFICATION_CODE` - Verification/auth codes
- `PASSWORD` - Passwords
- `BANK_ACCOUNT_LAST_DIGITS` - Bank account digits

### How to Add New Entity Type

1. **Add recognizer** in `utils/customer_registry.py`
2. **Map entity** in `redactConfig.yaml`
3. **Add replacement** in `config_dev.json` and `config_prod.json`

---

## File Structure Quick Reference

```
├── main.py                      ← Main pipeline logic
│   ├── DirectPIITransform       ← Core redaction class
│   │   ├── _is_false_positive() ← False positive filter
│   │   ├── _detect_password_context() ← Context detection
│   │   └── process()            ← Main processing logic
│   └── run()                    ← Pipeline execution
│
├── utils/
│   ├── customer_registry.py     ← Custom recognizers
│   │   ├── VerificationCodeRecognizer ← Password/code detection
│   │   ├── SpokenAddressRecognizer
│   │   ├── BankLastDigitsRecognizer
│   │   ├── SpokenPostcodeRecognizer
│   │   └── SpelledOutNameRecognizer
│   │
│   └── spoken_to_numeric.py     ← Text preprocessing
│       └── spoken_to_numeric()  ← Convert "thirty" → "30"
│
├── redactConfig.yaml            ← NLP & entity mapping
├── config_dev.json              ← Dev configuration
├── config_prod.json             ← Prod configuration
├── test_fixes.py                ← Test suite
└── test/
    ├── input.txt                ← Test input
    ├── output.txt               ← Expected output
    └── inspect_entity.py        ← spaCy debugging tool
```

---

## Performance Tuning

### If processing is too slow:

1. **Reduce batch size** in config:
```json
"processing": {
    "batch_size": 1000  // ← Reduce from 3000
}
```

2. **Limit selected fields**:
```json
"selected_fields": ["transaction_id", "transcription"]  // Only what's needed
```

3. **Increase worker count** (Dataflow only):
```bash
python main.py \
    --config_path config_prod.json \
    --runner DataflowRunner \
    --max_num_workers 50  # ← Increase workers
```

### If using too much memory:

1. **Use smaller spaCy model** in `redactConfig.yaml`:
```yaml
model_name: en_core_web_md  # Instead of en_core_web_lg
```

2. **Process fewer records**:
```json
"processing": {
    "limit": 100  // ← Reduce for testing
}
```

---

## Quick Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| "YOU'RE" still redacted | False positive list not loaded | Check `_is_false_positive()` is called |
| Password not detected | No matching pattern | Add pattern to `VerificationCodeRecognizer` |
| Too many false positives | Threshold too low | Increase score threshold |
| Missing real names | Threshold too high | Decrease score threshold |
| Import errors | Missing dependencies | `pip install -r requirements.txt` |
| spaCy model error | Model not downloaded | `python -m spacy download en_core_web_lg` |

---

## Best Practices

### ✅ DO:
- Test changes with `test_fixes.py` before deploying
- Use DirectRunner for local testing first
- Add debug logging when troubleshooting
- Document new patterns in code comments
- Keep false positive list alphabetically sorted
- Use uppercase for false positive words (all caps transcripts)

### ❌ DON'T:
- Deploy directly to production without testing
- Lower thresholds below 0.5 (too many false positives)
- Add overly broad regex patterns (performance impact)
- Remove existing patterns without testing impact
- Modify Presidio core code (use custom recognizers instead)

---

## Emergency Rollback

If fixes cause issues in production:

```bash
# 1. Revert git changes
git revert HEAD

# 2. Or restore specific files
git checkout HEAD~1 main.py
git checkout HEAD~1 utils/customer_registry.py

# 3. Redeploy
python main.py --config_path config_prod.json --runner DataflowRunner
```

---

## Useful Commands

```bash
# Download spaCy model
python -m spacy download en_core_web_lg

# Test entity detection on text
python test/inspect_entity.py "YOUR TEXT HERE"

# Run full test suite
python test_fixes.py

# Local test run
python main.py --config_path config_dev.json --runner DirectRunner

# Production deployment
python main.py --config_path config_prod.json --runner DataflowRunner

# Check Presidio version
pip show presidio-analyzer presidio-anonymizer

# View BigQuery results
bq query "SELECT * FROM dataset.td_call_redaction_p2 LIMIT 10"
```

---

## Support Resources

- **Presidio Docs**: https://microsoft.github.io/presidio/
- **spaCy Docs**: https://spacy.io/usage/linguistic-features
- **Apache Beam Docs**: https://beam.apache.org/documentation/
- **Regex Testing**: https://regex101.com/

---

Last Updated: 2025-11-03
