"""
Debug script to test email address redaction
"""
import json
import re
from utils.spoken_to_numeric import spoken_to_numeric
from utils.simplified_recognizers import SpokenEmailRecognizer

# Test data
conversation = [
    {"role":"Agent","content":"THANK YOU AND COULD YOU PLEASE HELP ME WITH YOUR EMAIL ADDRESS"},
    {"role":"Customer","content":"ASHMORE FOR AT SKY DOT COM"}
]

print("="*80)
print("Testing Email Recognition")
print("="*80)

recognizer = SpokenEmailRecognizer()

# Simulate what happens in main.py for each customer turn
previous_turns_text = []

for i, turn in enumerate(conversation):
    content = turn['content']
    role = turn['role']
    
    print(f"\n{'='*80}")
    print(f"Turn {i+1}: {role}")
    print(f"Original: {content}")
    
    converted_content = spoken_to_numeric(content)
    print(f"After spoken_to_numeric: {converted_content}")
    
    if role.lower() == 'agent':
        previous_turns_text.append(converted_content)
        print("→ AGENT TURN: Skipped PII analysis")
        continue
    
    # Build context-aware text
    if previous_turns_text:
        context_aware_text = " ".join(previous_turns_text) + " " + converted_content
        current_turn_offset = len(" ".join(previous_turns_text)) + 1
    else:
        context_aware_text = converted_content
        current_turn_offset = 0
    
    print(f"\nContext-aware text sent to analyzer:")
    print(f"  '{context_aware_text}'")
    print(f"  Current turn starts at offset: {current_turn_offset}")
    print(f"  Current turn: '{converted_content}'")
    
    # Debug checks
    text_upper = context_aware_text.upper()
    print(f"\nDebug checks:")
    print(f"  - Text upper: '{text_upper}'")
    print(f"  - Has 'AT': {'AT' in text_upper}")
    print(f"  - Has 'DOT': {'DOT' in text_upper}")
    print(f"  - Has 'FOR': {'FOR' in text_upper}")
    print(f"  - Has 'EMAIL': {'EMAIL' in text_upper}")
    
    # Test the email patterns
    email_patterns = [
        # "WORD AT DOMAIN DOT COM/CO DOT UK"
        r'\b[A-Z]+(?:\s+[A-Z]+)?\s+(?:AT|@)\s+[A-Z]+(?:\s+DOT\s+[A-Z]+)+\b',
        # "WORD FOR AT DOMAIN DOT COM" (FOR is common filler word)
        r'\b[A-Z]+\s+FOR\s+AT\s+[A-Z]+(?:\s+DOT\s+[A-Z]+)+\b',
    ]
    
    print(f"\nTesting email patterns:")
    for idx, pattern in enumerate(email_patterns, 1):
        print(f"  Pattern {idx}: {pattern}")
        matches = list(re.finditer(pattern, text_upper))
        if matches:
            print(f"    ✅ MATCHED!")
            for match in matches:
                print(f"      - Position {match.start()}-{match.end()}: '{match.group()}'")
        else:
            print(f"    ❌ No match")
    
    # Analyze with recognizer
    print(f"\nCalling SpokenEmailRecognizer.analyze()...")
    results = recognizer.analyze(context_aware_text, None, None)
    
    print(f"\nRecognizer results:")
    if results:
        for r in results:
            print(f"  - Entity: {r.entity_type}, Start: {r.start}, End: {r.end}, Score: {r.score}")
            print(f"    Matched text: '{context_aware_text[r.start:r.end]}'")
            print(f"    In current turn? {r.start >= current_turn_offset}")
            
            if r.start >= current_turn_offset:
                adjusted_start = r.start - current_turn_offset
                adjusted_end = r.end - current_turn_offset
                print(f"    Adjusted for current turn: start={adjusted_start}, end={adjusted_end}")
                print(f"    Would redact: '{converted_content[adjusted_start:adjusted_end]}'")
    else:
        print("  ❌ NO RESULTS FOUND!")
    
    # Add to previous turns
    previous_turns_text.append(converted_content)

print("\n" + "="*80)
