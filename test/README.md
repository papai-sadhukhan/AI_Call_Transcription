# Test Directory

This directory contains test data and utilities for the PII redaction system.

## Files

### `input.txt`
Sample conversation transcript in JSON format (original, unredacted).

**Format**: Array of conversation turns
```json
[
  {"role":"Agent","content":"HELLO MY NAME IS JOHN"},
  {"role":"Customer","content":"HI THERE"}
]
```

### `output.txt`
Expected output after PII redaction (reference).

### `inspect_entity.py`
Utility script to inspect what entities spaCy's NER model detects in text.

**Usage**:
```bash
python test/inspect_entity.py "YOUR TEXT HERE"
```

**Example**:
```bash
python test/inspect_entity.py "MY NAME IS JOHN SMITH"
# Output:
# Text: MY NAME IS JOHN SMITH
# Entities:
# JOHN SMITH -> PERSON
```

## Running Tests

### Main Test Suite
Located in project root: `test_fixes.py`

```bash
# Run all tests
python test_fixes.py

# Expected output:
# ✅ PASSED: Issue #1: YOU'RE False Positive
# ✅ PASSED: Issue #2: Alphanumeric Password
# ✅ PASSED: Comprehensive Tests
```

### Manual Testing

1. **Test entity detection**:
```bash
python test/inspect_entity.py "YOU'RE WELCOME MY NAME IS JOHN"
```

2. **Test full pipeline** (with actual input.txt):
```bash
# Create a simple test script
python -c "
import json
from main import DirectPIITransform

with open('test/input.txt') as f:
    transcript = json.loads(f.read())

config = {'pii_entities': {'PERSON': '#####', 'PASSWORD': '#####'}}
transform = DirectPIITransform(config)
transform.setup()

element = {'conversation_transcript': transcript}
results = list(transform.process(element))

print(json.dumps(results[0]['conversation_transcript'], indent=2))
"
```

## Test Data Scenarios

### Current Coverage in input.txt

1. **Agent Introduction**: Name detection
2. **Technical Issue**: Mixed content
3. **Password Request**: Verification context
4. **Spelled Password**: "CAPITAL X J L TWO ONE FIVE M E"
5. **Numbers in Speech**: "THIRTY YEARS", "TWO SECONDS"

### Recommended Additional Test Cases

Create additional test files for:

1. **false_positives.txt**: Pronouns and contractions
```json
[
  {"role":"Agent","content":"YOU'RE WELCOME"},
  {"role":"Agent","content":"I'M HERE TO HELP"},
  {"role":"Agent","content":"WE'RE READY"}
]
```

2. **passwords.txt**: Various password formats
```json
[
  {"role":"Customer","content":"PASSWORD IS ABC123"},
  {"role":"Customer","content":"CODE IS A B C 1 2 3"},
  {"role":"Customer","content":"CAPITAL X Y Z 456"}
]
```

3. **mixed_pii.txt**: Multiple PII types
```json
[
  {"role":"Customer","content":"NAME IS JOHN EMAIL IS JOHN@EMAIL.COM PHONE 07700900123"}
]
```

## Creating New Tests

### Template for test_fixes.py

```python
def test_your_new_case():
    """Test description"""
    print("\nTEST: Your Test Name")
    
    original = [{"role":"Agent","content":"YOUR TEST TEXT"}]
    element = {"conversation_transcript": original}
    config = {"pii_entities": {"PERSON": "#####"}}
    
    transform = DirectPIITransform(config)
    transform.setup()
    results = list(transform.process(element))
    
    actual = results[0]["conversation_transcript"][0]["content"]
    expected = "YOUR EXPECTED TEXT"
    
    if actual == expected:
        print("✅ PASSED")
        return True
    else:
        print(f"❌ FAILED: Expected '{expected}', got '{actual}'")
        return False
```

## Debugging Tips

### 1. See Raw Entity Detection
```bash
# Shows what spaCy detects before filtering
python test/inspect_entity.py "YOUR TEXT"
```

### 2. Check Conversion
```python
from utils.spoken_to_numeric import spoken_to_numeric
text = "THIRTY YEARS TWO SECONDS"
print(spoken_to_numeric(text))
# Output: "30 YEARS 2 SECONDS"
```

### 3. Test Pattern Matching
```python
import re
pattern = r'\b(?:CAPITAL\s+)?(?:[A-Z]\s+){2,}[A-Z0-9](?:\s+[A-Z0-9]){2,}\b'
text = "PASSWORD IS CAPITAL X J L 215 M E"
matches = list(re.finditer(pattern, text))
for m in matches:
    print(f"Match: {m.group()} at position {m.start()}-{m.end()}")
```

### 4. Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
# Then run your tests
```

## Common Issues

### Issue: spaCy model not found
```bash
# Solution:
python -m spacy download en_core_web_lg
```

### Issue: Import errors
```bash
# Make sure you're in project root:
cd /path/to/skydata-genai-tf
python test/inspect_entity.py "text"
```

### Issue: Different results than expected
1. Check spaCy version: `python -c "import spacy; print(spacy.__version__)"`
2. Check model version: `python -m spacy info en_core_web_lg`
3. Verify false positive list is loaded
4. Check threshold values

## Test Maintenance

### When to Update Tests

1. **New false positive found**: Add to test suite
2. **New PII pattern**: Create test case
3. **Bug found**: Add regression test
4. **New entity type**: Add coverage

### Test Review Checklist

- [ ] All tests pass
- [ ] Cover both issues from requirements
- [ ] Include edge cases
- [ ] Test false positives
- [ ] Test true positives
- [ ] Document expected behavior
- [ ] Include error cases

## Quick Commands

```bash
# Run all tests
python test_fixes.py

# Inspect specific text
python test/inspect_entity.py "YOUR TEXT HERE"

# Check spaCy installation
python -c "import spacy; nlp = spacy.load('en_core_web_lg'); print('✅ OK')"

# Verify Presidio
python -c "from presidio_analyzer import AnalyzerEngine; print('✅ OK')"

# Test conversion
python -c "from utils.spoken_to_numeric import spoken_to_numeric; print(spoken_to_numeric('THIRTY YEARS'))"
```

---

For more information:
- Main test suite: `../test_fixes.py`
- Documentation: `../FIXES_SUMMARY.md`
- Quick reference: `../QUICK_REFERENCE.md`
