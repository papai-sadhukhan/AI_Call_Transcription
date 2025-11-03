"""
Test script to verify PII redaction fixes for the two reported issues.
"""
import json
import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Suppress Presidio warnings
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)

from main import DirectPIITransform
from utils.spoken_to_numeric import spoken_to_numeric
from utils.customer_registry import FalsePositiveFilterRecognizer, AlphanumericPasswordRecognizer

def test_issue_1_youre_false_positive():
    """
    Test Issue #1: False positive on "YOU'RE"
    Should NOT redact "YOU'RE" as it's a pronoun, not a person name.
    """
    print("\n" + "="*80)
    print("TEST 1: False Positive - YOU'RE")
    print("="*80)
    
    original = [{"role":"Agent","content":"YOU'RE WELCOME BYE HAVE A NICE DAY"}]
    
    # Create test element
    element = {
        "transaction_id": "TEST001",
        "file_date": "2025-11-03",
        "conversation_transcript": original
    }
    
    # Create config
    config = {
        "pii_entities": {
            "PERSON": "#####",
            "PASSWORD": "#####"
        }
    }
    
    # Create and setup transform
    transform = DirectPIITransform(config)
    transform.setup()
    
    # Process
    results = list(transform.process(element))
    redacted_conversation = results[0]["conversation_transcript"]
    
    print(f"\n📝 Original:")
    print(json.dumps(original, indent=2))
    
    print(f"\n✅ After Redaction:")
    print(json.dumps(redacted_conversation, indent=2))
    
    print(f"\n🔍 Matched Entities:")
    print(results[0].get("redacted_entity", "None"))
    
    # Verify
    expected_content = "YOU'RE WELCOME BYE HAVE A NICE DAY"
    actual_content = redacted_conversation[0]["content"]
    
    if actual_content == expected_content:
        print("\n✅ TEST PASSED: 'YOU'RE' was correctly NOT redacted")
        return True
    else:
        print(f"\n❌ TEST FAILED: Expected '{expected_content}', got '{actual_content}'")
        return False


def test_issue_2_alphanumeric_password():
    """
    Test Issue #2: Alphanumeric password not being redacted
    Should redact "CAPITAL X J L TWO ONE FIVE M E" pattern.
    """
    print("\n" + "="*80)
    print("TEST 2: Alphanumeric Password Redaction")
    print("="*80)
    
    original = [
        {"role":"Agent","content":"THANK YOU AND ARE YOU THE ACCOUNT HOLDER OKAY CAN YOU PLEASE GIVE ME THE VERBAL PASSWORD FOR THIS ACCOUNT"},
        {"role":"Customer","content":"I DON'T KNOW WHAT THE PASSWORD IS TO BE HONEST WITH YOU I DON'T THINK I'VE HAD IT FOR SO LONG SKY I'VE HAD IT FOR THIRTY YEARS LET ME KNOW WHAT THE PASSWORD IS HANG ON TWO SECONDS WRITTEN DOWN SKY SKY GO SKY SKY"},
        {"role":"Agent","content":"IF YOU CANNOT FIND IT I CAN ASK YOU ANOTHER QUESTION"},
        {"role":"Customer","content":"I'VE GOT ONE HERE I'M NOT SURE IF THIS IS IT BUT THIS IS THE LAST TIME GOT WRITTEN DOWN CAPITAL X J L TWO ONE FIVE M E"}
    ]
    
    # Create test element
    element = {
        "transaction_id": "TEST002",
        "file_date": "2025-11-03",
        "conversation_transcript": original
    }
    
    # Create config
    config = {
        "pii_entities": {
            "PERSON": "#####",
            "PASSWORD": "#####",
            "VERIFICATION_CODE": "#####"
        }
    }
    
    # Create and setup transform
    transform = DirectPIITransform(config)
    transform.setup()
    
    # Process
    results = list(transform.process(element))
    redacted_conversation = results[0]["conversation_transcript"]
    
    print(f"\n📝 Original (last turn):")
    print(json.dumps(original[-1], indent=2))
    
    print(f"\n✅ After Redaction (last turn):")
    print(json.dumps(redacted_conversation[-1], indent=2))
    
    print(f"\n🔍 Matched Entities:")
    print(results[0].get("redacted_entity", "None"))
    
    # Check conversion
    print(f"\n🔄 After spoken_to_numeric conversion:")
    converted = spoken_to_numeric(original[-1]["content"])
    print(converted)
    
    # Verify - the password part should be redacted
    actual_content = redacted_conversation[-1]["content"]
    
    # Check if the alphanumeric code is redacted
    if "CAPITAL" in actual_content and "#####" in actual_content:
        # Pattern partially redacted - check if the code part is gone
        if "X J L 215 M E" not in actual_content and "XJL215ME" not in actual_content:
            print("\n✅ TEST PASSED: Alphanumeric password was redacted")
            return True
        else:
            print(f"\n⚠️  TEST PARTIAL: Some redaction occurred but code still visible: {actual_content}")
            return False
    elif actual_content.count("#####") >= 1:
        print("\n✅ TEST PASSED: Password pattern was redacted")
        return True
    else:
        print(f"\n❌ TEST FAILED: Password was not redacted. Content: {actual_content}")
        return False


def test_comprehensive():
    """
    Comprehensive test with various edge cases.
    """
    print("\n" + "="*80)
    print("TEST 3: Comprehensive Edge Cases")
    print("="*80)
    
    test_cases = [
        {
            "name": "Pronoun I'M",
            "content": "I'M CALLING ABOUT MY ACCOUNT",
            "should_contain": "I'M",
            "should_not_contain": "#####"
        },
        {
            "name": "Pronoun WE'RE",
            "content": "WE'RE HAPPY TO HELP YOU TODAY",
            "should_contain": "WE'RE",
            "should_not_contain": "#####"
        },
        {
            "name": "Actual name",
            "content": "MY NAME IS JOHN SMITH",
            "should_contain": "#####",
            "should_not_contain": "JOHN"
        },
        {
            "name": "Numeric code with password context",
            "content": "MY PASSWORD IS 123456",
            "should_contain": "#####",
            "should_not_contain": "123456"
        }
    ]
    
    config = {
        "pii_entities": {
            "PERSON": "#####",
            "PASSWORD": "#####",
            "VERIFICATION_CODE": "#####"
        }
    }
    
    transform = DirectPIITransform(config)
    transform.setup()
    
    passed = 0
    failed = 0
    
    for test in test_cases:
        print(f"\n  Testing: {test['name']}")
        print(f"  Original: {test['content']}")
        
        element = {
            "transaction_id": "TEST_COMP",
            "file_date": "2025-11-03",
            "conversation_transcript": [{"role": "Agent", "content": test['content']}]
        }
        
        results = list(transform.process(element))
        redacted_content = results[0]["conversation_transcript"][0]["content"]
        
        print(f"  Redacted: {redacted_content}")
        
        # Check assertions
        success = True
        if test.get("should_contain"):
            if test["should_contain"] not in redacted_content:
                print(f"  ❌ FAILED: Should contain '{test['should_contain']}'")
                success = False
        
        if test.get("should_not_contain"):
            if test["should_not_contain"] in redacted_content:
                print(f"  ❌ FAILED: Should NOT contain '{test['should_not_contain']}'")
                success = False
        
        if success:
            print(f"  ✅ PASSED")
            passed += 1
        else:
            failed += 1
    
    print(f"\n{'='*80}")
    print(f"Comprehensive Tests: {passed} passed, {failed} failed")
    print(f"{'='*80}")
    
    return failed == 0


def test_issue_3_spelled_names():
    """
    Test Issue #3: Spelled-out names not fully redacted
    Should redact "A P P L E" and "R O S E" when in name context.
    """
    print("\n" + "="*80)
    print("TEST 4: Spelled-Out Names")
    print("="*80)
    
    original = [
        {"role":"Agent","content":"MAY I KNOW YOUR FULL NAME PLEASE"},
        {"role":"Customer","content":"MY NAME IS MISSUS A P P L E THAT'S MY CHRISTIAN NAME AND MY SURNAME IS R O S E"}
    ]
    
    element = {
        "transaction_id": "TEST003",
        "file_date": "2025-11-03",
        "conversation_transcript": original
    }
    
    config = {
        "pii_entities": {
            "PERSON": "#####",
            "PASSWORD": "#####"
        }
    }
    
    transform = DirectPIITransform(config)
    transform.setup()
    
    results = list(transform.process(element))
    redacted_conversation = results[0]["conversation_transcript"]
    
    print(f"\n📝 Original (response):")
    print(json.dumps(original[1], indent=2))
    
    print(f"\n✅ After Redaction (response):")
    print(json.dumps(redacted_conversation[1], indent=2))
    
    print(f"\n🔍 Matched Entities:")
    print(results[0].get("redacted_entity", "None"))
    
    # Verify - spelled names should be redacted
    actual_content = redacted_conversation[1]["content"]
    
    if "A P P L E" not in actual_content and "R O S E" not in actual_content:
        print("\n✅ TEST PASSED: Spelled-out names were redacted")
        return True
    else:
        print(f"\n❌ TEST FAILED: Spelled names still visible: {actual_content}")
        return False


def test_issue_4_full_address():
    """
    Test Issue #4: Address not fully redacted
    Should redact entire address line including postcode.
    """
    print("\n" + "="*80)
    print("TEST 5: Full Address Redaction")
    print("="*80)
    
    original = [
        {"role":"Agent","content":"THANK YOU SO MUCH THE FIRST LINE OF THE ADDRESS AND THE POST CODE"},
        {"role":"Customer","content":"TWENTY NINE LAMPTON AVENUE S S TWO FIVE N X"}
    ]
    
    element = {
        "transaction_id": "TEST004",
        "file_date": "2025-11-03",
        "conversation_transcript": original
    }
    
    config = {
        "pii_entities": {
            "ADDRESS": "#####",
            "POSTAL_CODE": "#####"
        }
    }
    
    transform = DirectPIITransform(config)
    transform.setup()
    
    results = list(transform.process(element))
    redacted_conversation = results[0]["conversation_transcript"]
    
    print(f"\n📝 Original (response):")
    print(json.dumps(original[1], indent=2))
    
    print(f"\n✅ After Redaction (response):")
    print(json.dumps(redacted_conversation[1], indent=2))
    
    print(f"\n🔍 Matched Entities:")
    print(results[0].get("redacted_entity", "None"))
    
    # Verify - address should be significantly redacted
    actual_content = redacted_conversation[1]["content"]
    
    if "LAMPTON" not in actual_content and "#####" in actual_content:
        print("\n✅ TEST PASSED: Address was redacted")
        return True
    else:
        print(f"\n❌ TEST FAILED: Address still visible: {actual_content}")
        return False


def test_issue_5_maiden_name():
    """
    Test Issue #5: Mother's maiden name not redacted
    Should redact single name after "maiden name" question.
    """
    print("\n" + "="*80)
    print("TEST 6: Mother's Maiden Name")
    print("="*80)
    
    original = [
        {"role":"Agent","content":"CAN YOU PLEASE TELL ME YOUR MOTHER'S MAIDEN NAME THERE"},
        {"role":"Customer","content":"NINA"}
    ]
    
    element = {
        "transaction_id": "TEST005",
        "file_date": "2025-11-03",
        "conversation_transcript": original
    }
    
    config = {
        "pii_entities": {
            "PERSON": "#####"
        }
    }
    
    transform = DirectPIITransform(config)
    transform.setup()
    
    results = list(transform.process(element))
    redacted_conversation = results[0]["conversation_transcript"]
    
    print(f"\n📝 Original (response):")
    print(json.dumps(original[1], indent=2))
    
    print(f"\n✅ After Redaction (response):")
    print(json.dumps(redacted_conversation[1], indent=2))
    
    print(f"\n🔍 Matched Entities:")
    print(results[0].get("redacted_entity", "None"))
    
    # Verify - name should be redacted
    actual_content = redacted_conversation[1]["content"]
    
    if "NINA" not in actual_content and "#####" in actual_content:
        print("\n✅ TEST PASSED: Maiden name was redacted")
        return True
    else:
        print(f"\n❌ TEST FAILED: Maiden name still visible: {actual_content}")
        return False


if __name__ == "__main__":
    print("\n" + "="*80)
    print("PII REDACTION FIX VALIDATION")
    print("="*80)
    
    results = []
    
    # Run tests
    try:
        results.append(("Issue #1: YOU'RE False Positive", test_issue_1_youre_false_positive()))
    except Exception as e:
        print(f"\n❌ TEST 1 CRASHED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Issue #1: YOU'RE False Positive", False))
    
    try:
        results.append(("Issue #2: Alphanumeric Password", test_issue_2_alphanumeric_password()))
    except Exception as e:
        print(f"\n❌ TEST 2 CRASHED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Issue #2: Alphanumeric Password", False))
    
    try:
        results.append(("Comprehensive Tests", test_comprehensive()))
    except Exception as e:
        print(f"\n❌ TEST 3 CRASHED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Comprehensive Tests", False))
    
    try:
        results.append(("Issue #3: Spelled-Out Names", test_issue_3_spelled_names()))
    except Exception as e:
        print(f"\n❌ TEST 4 CRASHED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Issue #3: Spelled-Out Names", False))
    
    try:
        results.append(("Issue #4: Full Address", test_issue_4_full_address()))
    except Exception as e:
        print(f"\n❌ TEST 5 CRASHED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Issue #4: Full Address", False))
    
    try:
        results.append(("Issue #5: Maiden Name", test_issue_5_maiden_name()))
    except Exception as e:
        print(f"\n❌ TEST 6 CRASHED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Issue #5: Maiden Name", False))
    
    # Summary
    print("\n" + "="*80)
    print("FINAL RESULTS")
    print("="*80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print(f"\n{total_passed}/{total_tests} test suites passed")
    
    if total_passed == total_tests:
        print("\n🎉 All tests passed! The fixes are working correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")
        sys.exit(1)
