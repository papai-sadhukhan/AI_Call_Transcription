"""
Debug script to test address redaction
"""
import json
import re
from utils.spoken_to_numeric import spoken_to_numeric
from utils.simplified_recognizers import ContextAwareAddressRecognizer

# Test data
conversation = [
    {"role":"Agent","content":"LET'S HAVE A LOOK CAN I TAKE YOUR FULL NAME ADDRESS AND POST CODE"},
    {"role":"Customer","content":"YES SORRY SO THE ADDRESS IS SEVEN FOURTY TWO A"},
    {"role":"Agent","content":"YEAH"},
    {"role":"Customer","content":"FLAT THREE MEASURE APARTMENT"}
]

print("="*80)
print("Testing Address Recognition")
print("="*80)

recognizer = ContextAwareAddressRecognizer()

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
    has_numbers = bool(re.search(r'\d+', context_aware_text))
    print(f"\nDebug checks:")
    print(f"  - Has 'FLAT': {'FLAT' in text_upper}")
    print(f"  - Has 'APARTMENT': {'APARTMENT' in text_upper}")
    print(f"  - Has 'ADDRESS IS': {'ADDRESS IS' in text_upper}")
    print(f"  - Has numbers: {has_numbers}")
    print(f"  - Word count: {len(context_aware_text.split())}")
    
    # Analyze
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
        print("  NO RESULTS FOUND!")
    
    # Add to previous turns
    previous_turns_text.append(converted_content)

print("\n" + "="*80)
