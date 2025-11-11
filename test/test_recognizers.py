"""
Test script to verify password and name recognizers work correctly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.entity_recognizers import (
    ConversationContextTracker,
    StatefulPasswordRecognizer,
    StatefulNameRecognizer
)

# Load context indicators (mimicking config)
context_indicators = {
    "password": [
        "PASSWORD",
        "PASS WORD",
        "PASSCODE",
        "VERIFICATION CODE",
        "PIN"
    ],
    "name": [
        "NAME",
        "CALLED",
        "SURNAME",
        "FIRST NAME",
        "MAIDEN NAME"
    ],
    "number_words": [
        "ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", 
        "SIX", "SEVEN", "EIGHT", "NINE", "TEN"
    ]
}

# Test Password Recognition
print("=" * 80)
print("TEST 1: Password Recognition")
print("=" * 80)

context_tracker = ConversationContextTracker(context_indicators)
password_recognizer = StatefulPasswordRecognizer(context_tracker, context_indicators)

# Simulate agent asking for password
agent_text = "OKAY ALSO CAN YOU VERIFY YOUR SKY ACCOUNT PASSWORD"
context_tracker.update_context(agent_text)
print(f"Agent: {agent_text}")
print(f"Context tracker expecting_password: {context_tracker.expecting_password}")

# Customer provides password
customer_text = "WITH THE NEW ONE THEY GAVE ME IS GOT IT WRITTEN DOWN HERE SOMEWHERE THREE THREE TWO C D C Q I J SEVEN SIX EIGHT E"
print(f"\nCustomer: {customer_text}")

results = password_recognizer.analyze(customer_text, [], None)
print(f"\nResults found: {len(results)}")
for r in results:
    print(f"  - Entity: {r.entity_type}, Score: {r.score}")
    print(f"    Start: {r.start}, End: {r.end}")
    print(f"    Matched text: '{customer_text[r.start:r.end]}'")
    print(f"    Pattern: {r.analysis_explanation.pattern_name}")

# Test Name Recognition
print("\n" + "=" * 80)
print("TEST 2: Name Recognition (Mother's Maiden Name)")
print("=" * 80)

context_tracker2 = ConversationContextTracker(context_indicators)
name_recognizer = StatefulNameRecognizer(context_tracker2, context_indicators)

# Simulate agent asking for maiden name
agent_text2 = "CAN TRY WITH YOUR MOTHER'S MAIDEN NAME"
context_tracker2.update_context(agent_text2)
print(f"Agent: {agent_text2}")
print(f"Context tracker expecting_name: {context_tracker2.expecting_name}")

# Customer provides name
customer_text2 = "GREY G R A C E"
print(f"\nCustomer: {customer_text2}")

results2 = name_recognizer.analyze(customer_text2, [], None)
print(f"\nResults found: {len(results2)}")
for r in results2:
    print(f"  - Entity: {r.entity_type}, Score: {r.score}")
    print(f"    Start: {r.start}, End: {r.end}")
    print(f"    Matched text: '{customer_text2[r.start:r.end]}'")
    print(f"    Pattern: {r.analysis_explanation.pattern_name}")

print("\n" + "=" * 80)
print("TEST 3: Name Recognition (Spelled out only)")
print("=" * 80)

context_tracker3 = ConversationContextTracker(context_indicators)
name_recognizer3 = StatefulNameRecognizer(context_tracker3, context_indicators)

# Simulate agent asking for name
agent_text3 = "CAN YOU SPELL YOUR FIRST NAME"
context_tracker3.update_context(agent_text3)
print(f"Agent: {agent_text3}")
print(f"Context tracker expecting_name: {context_tracker3.expecting_name}")

# Customer provides spelled name
customer_text3 = "G R A C E"
print(f"\nCustomer: {customer_text3}")

results3 = name_recognizer3.analyze(customer_text3, [], None)
print(f"\nResults found: {len(results3)}")
for r in results3:
    print(f"  - Entity: {r.entity_type}, Score: {r.score}")
    print(f"    Start: {r.start}, End: {r.end}")
    print(f"    Matched text: '{customer_text3[r.start:r.end]}'")
    print(f"    Pattern: {r.analysis_explanation.pattern_name}")

print("\n" + "=" * 80)
print("TESTS COMPLETE")
print("=" * 80)
