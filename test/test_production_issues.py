"""
Test cases for production issues reported.
Tests Flair-based NER approach vs custom logic.
"""
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import DirectPIITransform

config = {
    "pii_entities": {
        "PERSON": "#####",
        "PASSWORD": "#####",
        "EMAIL_ADDRESS": "####",
        "BANK_ACCOUNT_LAST_DIGITS": "####",
        "ADDRESS": "####",
        "UK_POSTCODE": "####"
    }
}

def test_case(name, conversation, expected_outputs):
    """Test a single case and report results."""
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print(f"{'='*80}")
    
    element = {
        "transaction_id": "TEST",
        "file_date": "2025-11-03",
        "conversation_transcript": conversation
    }
    
    transform = DirectPIITransform(config)
    transform.setup()
    
    results = list(transform.process(element))
    redacted = results[0]["conversation_transcript"]
    
    print(f"\n📝 Input:")
    for i, turn in enumerate(conversation):
        print(f"  [{i}] {turn['role']}: {turn['content']}")
    
    print(f"\n✅ Actual Output:")
    for i, turn in enumerate(redacted):
        print(f"  [{i}] {turn['role']}: {turn['content']}")
    
    print(f"\n🎯 Expected Output:")
    for i, expected in enumerate(expected_outputs):
        print(f"  [{i}] {expected['role']}: {expected['content']}")
    
    # Compare
    passed = True
    for i, (actual, expected) in enumerate(zip(redacted, expected_outputs)):
        if actual['content'] != expected['content']:
            passed = False
            print(f"\n❌ Mismatch at turn {i} ({actual['role']}):")
            print(f"   Expected: {expected['content']}")
            print(f"   Got:      {actual['content']}")
    
    if passed:
        print(f"\n✅ TEST PASSED")
    else:
        print(f"\n❌ TEST FAILED")
    
    return passed


# Test 1: Person Name Incorrect - "THANK" and "HOW" incorrectly detected as names
test1_input = [
    {"role": "Agent", "content": "HELLO THANK YOU FOR REACHING SKY MY NAME IS HOW CAN I HELP YOU"}
]

test1_expected = [
    {"role": "Agent", "content": "HELLO THANK YOU FOR REACHING SKY MY NAME IS HOW CAN I HELP YOU"}
]

# Test 2: Bank Account Last Digits - "DOUBLE ZERO" should be redacted
test2_input = [
    {"role": "Agent", "content": "AND CAN YOU JUST CONFIRM THE LAST TWO DIGITS OF THE BANK ACCOUNT NUMBER YOU PAY THE BILL WITH"},
    {"role": "Customer", "content": "YEAH IT'S DOUBLE ZERO SIR"}
]

test2_expected = [
    {"role": "Agent", "content": "AND CAN YOU JUST CONFIRM THE LAST 2 DIGITS OF THE BANK ACCOUNT NUMBER YOU PAY THE BILL WITH"},
    {"role": "Customer", "content": "YEAH IT'S #### SIR"}
]

# Test 3: Address and Postcode - Multiple address components should be redacted
test3_input = [
    {"role": "Agent", "content": "LET'S HAVE A LOOK CAN I TAKE YOUR FULL NAME ADDRESS AND POST CODE"},
    {"role": "Customer", "content": "YES SORRY SO THE ADDRESS IS SEVEN FOURTY TWO A"},
    {"role": "Agent", "content": "YEAH"},
    {"role": "Customer", "content": "FLAT THREE MEASURE APARTMENT"},
    {"role": "Agent", "content": "YEAH"},
    {"role": "Customer", "content": "TRADE AGREEMENT YEAH"},
    {"role": "Agent", "content": "AND THE POST CODE"},
    {"role": "Customer", "content": "TWENTY ONE X"},
    {"role": "Agent", "content": "GREAT AND WHAT'S YOUR FULL NAME"},
    {"role": "Customer", "content": "SCARING ME IN"},
    {"role": "Agent", "content": "YEAH AND ARE YOU THE ACCOUNT HOLDER"},
    {"role": "Customer", "content": "YES SIR"}
]

test3_expected = [
    {"role": "Agent", "content": "LET'S HAVE A LOOK CAN I TAKE YOUR FULL NAME ADDRESS AND POST CODE"},
    {"role": "Customer", "content": "YES SORRY SO THE ADDRESS IS ####"},
    {"role": "Agent", "content": "YEAH"},
    {"role": "Customer", "content": "####"},
    {"role": "Agent", "content": "YEAH"},
    {"role": "Customer", "content": "TRADE AGREEMENT YEAH"},
    {"role": "Agent", "content": "AND THE POST CODE"},
    {"role": "Customer", "content": "####"},
    {"role": "Agent", "content": "GREAT AND WHAT'S YOUR FULL NAME"},
    {"role": "Customer", "content": "####"},
    {"role": "Agent", "content": "YEAH AND ARE YOU THE ACCOUNT HOLDER"},
    {"role": "Customer", "content": "YES SIR"}
]

# Test 4: Email Address - Spoken email should be redacted
test4_input = [
    {"role": "Agent", "content": "THANK YOU AND COULD YOU PLEASE HELP ME WITH YOUR EMAIL ADDRESS"},
    {"role": "Customer", "content": "ASHMORE FOR AT SKY DOT COM"}
]

test4_expected = [
    {"role": "Agent", "content": "THANK YOU AND COULD YOU PLEASE HELP ME WITH YOUR EMAIL ADDRESS"},
    {"role": "Customer", "content": "####"}
]

if __name__ == "__main__":
    print("="*80)
    print("PRODUCTION ISSUES TEST SUITE")
    print("="*80)
    
    results = []
    
    results.append(test_case(
        "Issue 1: Person Name Incorrect (THANK/HOW)",
        test1_input,
        test1_expected
    ))
    
    results.append(test_case(
        "Issue 2: Bank Account Last Digits (DOUBLE ZERO)",
        test2_input,
        test2_expected
    ))
    
    results.append(test_case(
        "Issue 3: Address and Postcode",
        test3_input,
        test3_expected
    ))
    
    results.append(test_case(
        "Issue 4: Email Address",
        test4_input,
        test4_expected
    ))
    
    print(f"\n{'='*80}")
    print("FINAL RESULTS")
    print(f"{'='*80}")
    print(f"Test 1 (Person Name): {'✅ PASSED' if results[0] else '❌ FAILED'}")
    print(f"Test 2 (Bank Digits): {'✅ PASSED' if results[1] else '❌ FAILED'}")
    print(f"Test 3 (Address): {'✅ PASSED' if results[2] else '❌ FAILED'}")
    print(f"Test 4 (Email): {'✅ PASSED' if results[3] else '❌ FAILED'}")
    print(f"\nOverall: {sum(results)}/{len(results)} tests passed")
