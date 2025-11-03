"""
Test with real examples from the user
"""
import json
from main import DirectPIITransform

# Test case 1: Agent introduction with name
test1_conversation = [
    {"role":"Agent","content":"HELLO THERE THANK YOU FOR CALLING SKY MY NAME IS ORANGE HOW CAN I HELP YOU TODAY"},
    {"role":"Customer","content":"HELLO APPLE NOTICE YOUNG LADY AND MY CONTRACT I TOOK OUT IN FEBRUARY TWO THOUSAND TWENTY FIVE THEN I NOTICED THAT IT'S GONE UP A THE THE POUND BUT I'VE RUNG TO SAY THAT MY HIGH FIBRE INSTALLED TODAY AND NOW MY LANDLINE IS NOT WORKING IT'S NO GOOD I THINK I'VE GOTTA BUY A NEW PHONE"}
]

# Test case 2: Name spelling
test2_conversation = [
    {"role":"Agent","content":"MAY I KNOW YOUR FULL NAME PLEASE"},
    {"role":"Customer","content":"MY NAME IS MISSUS APPLE A P P L E THAT'S MY CHRISTIAN NAME AND MY SURNAME IS ROSE R O S E"}
]

config = {
    "pii_entities": {
        "PERSON": "#####",
        "PASSWORD": "#####"
    }
}

def test_example(conversation, expected_agent, expected_customer, test_name):
    print(f"\n{'='*80}")
    print(f"TEST: {test_name}")
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
    
    print(f"\n📝 Original:")
    for turn in conversation:
        print(f"  {turn['role']}: {turn['content'][:100]}...")
    
    print(f"\n✅ Redacted:")
    for turn in redacted:
        print(f"  {turn['role']}: {turn['content'][:100]}...")
    
    print(f"\n🎯 Expected:")
    print(f"  Agent: {expected_agent[:100]}...")
    print(f"  Customer: {expected_customer[:100]}...")
    
    # Check results
    agent_match = expected_agent in redacted[0]["content"]
    customer_match = expected_customer in redacted[1]["content"]
    
    if agent_match and customer_match:
        print(f"\n✅ TEST PASSED")
        return True
    else:
        print(f"\n❌ TEST FAILED")
        if not agent_match:
            print(f"  Agent mismatch:")
            print(f"    Expected: {expected_agent}")
            print(f"    Got: {redacted[0]['content']}")
        if not customer_match:
            print(f"  Customer mismatch:")
            print(f"    Expected: {expected_customer}")
            print(f"    Got: {redacted[1]['content']}")
        return False

# Run tests
print("\n" + "="*80)
print("REAL WORLD EXAMPLE TESTS")
print("="*80)

test1_pass = test_example(
    test1_conversation,
    "HELLO THERE THANK YOU FOR CALLING SKY MY NAME IS ##### HOW CAN I HELP YOU TODAY",
    "HELLO ##### NOTICE YOUNG LADY AND MY CONTRACT",
    "Test 1: Agent Introduction"
)

test2_pass = test_example(
    test2_conversation,
    "MAY I KNOW YOUR FULL NAME PLEASE",
    "MY NAME IS ##### THAT'S MY CHRISTIAN NAME AND MY SURNAME IS #####",
    "Test 2: Name Spelling"
)

print("\n" + "="*80)
print("FINAL RESULTS")
print("="*80)
print(f"Test 1 (Agent Introduction): {'✅ PASSED' if test1_pass else '❌ FAILED'}")
print(f"Test 2 (Name Spelling): {'✅ PASSED' if test2_pass else '❌ FAILED'}")
print(f"\nOverall: {2 if test1_pass and test2_pass else 1 if test1_pass or test2_pass else 0}/2 tests passed")
