"""
Simplified recognizers without Flair dependency.
Uses improved pattern matching and context awareness.
"""
import re
from typing import List
from presidio_analyzer import (
    Pattern, PatternRecognizer, RecognizerResult, AnalysisExplanation
)

# -----------------------------------------------------------------------------
# 🚫 1. Strict False Positive Filter (minimal, trust spaCy more)
# -----------------------------------------------------------------------------
class StrictFalsePositiveFilter:
    """
    Very strict false positive filter - only filters obvious non-names.
    Trusts spaCy's NER more than custom logic.
    """
    
    # Only the most common false positives
    OBVIOUS_NON_NAMES = {
        "THANK", "THANKS", "HELLO", "HI", "THANKS", "PLEASE",
        "YES", "NO", "YEAH", "YEP", "OKAY", "OK", "HOW", "WHAT",
        "WHERE", "WHEN", "WHY", "WHO", "CAN", "COULD", "WOULD",
        "SHOULD", "YOU", "YOUR", "YOU'RE", "I", "I'M", "MY", "THE", "AND", "FOR", "BUT",
        "WE", "WE'RE", "THEY", "THEY'RE", "IT", "IT'S", "HE", "HE'S", "SHE", "SHE'S", "US"
    }
    
    @classmethod
    def is_false_positive(cls, text: str, entity_type: str, context: str) -> bool:
        """
        Only filter obvious false positives.
        """
        text_upper = text.upper().strip()
        
        if entity_type == "PERSON":
            # Filter obvious common words
            if text_upper in cls.OBVIOUS_NON_NAMES:
                return True
            
            # Filter single letters (unless in spelling context)
            if len(text_upper) == 1 and "SPELL" not in context.upper():
                return True
        
        return False


# -----------------------------------------------------------------------------
# 📧 2. Spoken Email Recognizer
# -----------------------------------------------------------------------------
class SpokenEmailRecognizer(PatternRecognizer):
    """
    Recognizes spoken email addresses (e.g., "JOHN AT SKY DOT COM").
    """
    
    EMAIL_CONTEXT_KEYWORDS = [
        "email", "e-mail", "e mail", "mail address", 
        "email address", "send to", "contact"
    ]
    
    def __init__(self):
        super().__init__(
            supported_entity="EMAIL_ADDRESS",
            supported_language="en",
            name="SpokenEmailRecognizer",
            context=self.EMAIL_CONTEXT_KEYWORDS,
            deny_list=["__PLACEHOLDER__"]
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """
        Detect spoken email patterns.
        Since main.py now passes full conversation context, find actual match positions.
        """
        results = []
        text_upper = text.upper()
        
        # Patterns for spoken email (very distinctive pattern with "AT" and "DOT")
        email_patterns = [
            # "WORD AT DOMAIN DOT COM/CO DOT UK"
            r'\b[A-Z]+(?:\s+[A-Z]+)?\s+(?:AT|@)\s+[A-Z]+(?:\s+DOT\s+[A-Z]+)+\b',
            # "WORD FOR AT DOMAIN DOT COM" (FOR is common filler word)
            r'\b[A-Z]+\s+FOR\s+AT\s+[A-Z]+(?:\s+DOT\s+[A-Z]+)+\b',
        ]
        
        # Find all email pattern matches and return their actual positions
        for pattern in email_patterns:
            for match in re.finditer(pattern, text_upper):
                results.append(RecognizerResult(
                    entity_type="EMAIL_ADDRESS",
                    start=match.start(),
                    end=match.end(),
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="spoken_email_pattern",
                        pattern=pattern,
                        original_score=0.95
                    )
                ))
        
        return results


# -----------------------------------------------------------------------------
# 🏦 3. Enhanced Bank Last Digits Recognizer
# -----------------------------------------------------------------------------
class EnhancedBankLastDigitsRecognizer(PatternRecognizer):
    """
    Recognizes bank account last digits including spoken forms like "DOUBLE ZERO".
    """
    
    BANK_CONTEXT_KEYWORDS = [
        "bank", "account", "last two digits", "last 2 digits",
        "ending with", "ends in", "account number", "last two", "last 2"
    ]
    
    # Mapping of spoken numbers
    SPOKEN_DIGITS = {
        "DOUBLE ZERO": "00", "DOUBLE ONE": "11", "DOUBLE TWO": "22",
        "DOUBLE THREE": "33", "DOUBLE FOUR": "44", "DOUBLE FIVE": "55",
        "DOUBLE SIX": "66", "DOUBLE SEVEN": "77", "DOUBLE EIGHT": "88",
        "DOUBLE NINE": "99", "DOUBLE OH": "00"
    }
    
    def __init__(self):
        super().__init__(
            supported_entity="BANK_ACCOUNT_LAST_DIGITS",
            supported_language="en",
            name="EnhancedBankLastDigitsRecognizer",
            context=self.BANK_CONTEXT_KEYWORDS,
            deny_list=["__PLACEHOLDER__"]
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """
        Detect bank account last digits in various spoken forms.
        """
        results = []
        text_upper = text.upper()
        
        # Check for bank/account context in last 300 chars
        context_start = max(0, len(text_upper) - 300)
        context_window = text_upper[context_start:].lower()
        
        has_bank_context = any(keyword in context_window for keyword in self.BANK_CONTEXT_KEYWORDS)
        
        if not has_bank_context:
            return results
        
        # Pattern 1: Spoken double digits (e.g., "DOUBLE ZERO" or after conversion "DOUBLE 0")
        for spoken, digit in self.SPOKEN_DIGITS.items():
            # Check both original form and partially converted form
            if spoken in text_upper:
                start = text_upper.find(spoken)
                end = start + len(spoken)
                results.append(RecognizerResult(
                    entity_type="BANK_ACCOUNT_LAST_DIGITS",
                    start=start,
                    end=end,
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="spoken_bank_digits",
                        pattern=f"spoken_{spoken}",
                        original_score=0.95
                    )
                ))
            else:
                # Check for partially converted form: "DOUBLE 0" instead of "DOUBLE ZERO"
                partial_form = "DOUBLE " + digit[-1]  # "DOUBLE 0"
                if partial_form in text_upper and len(digit) == 2 and digit[0] == digit[1]:
                    start = text_upper.find(partial_form)
                    end = start + len(partial_form)
                    results.append(RecognizerResult(
                        entity_type="BANK_ACCOUNT_LAST_DIGITS",
                        start=start,
                        end=end,
                        score=0.95,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="spoken_bank_digits_partial",
                            pattern=f"partial_{spoken}",
                            original_score=0.95
                        )
                    ))
        
        # Pattern 2: Regular 2-digit numbers in bank context
        digit_pattern = r'\b\d{2}\b'
        for match in re.finditer(digit_pattern, text_upper):
            # Avoid date-like matches
            context_snippet = text_upper[max(0, match.start()-20):match.end()+20]
            if not re.search(r'\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|TH|ST|ND|RD)\b', context_snippet):
                results.append(RecognizerResult(
                    entity_type="BANK_ACCOUNT_LAST_DIGITS",
                    start=match.start(),
                    end=match.end(),
                    score=0.85,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="bank_digits",
                        pattern=digit_pattern,
                        original_score=0.85
                    )
                ))
        
        return results


# -----------------------------------------------------------------------------
# 🏠 4. Context-Aware Address Recognizer
# -----------------------------------------------------------------------------
class ContextAwareAddressRecognizer(PatternRecognizer):
    """
    Recognizes addresses with strong context awareness.
    Redacts entire response when in address context.
    Now properly uses conversation context from main.py
    """
    
    ADDRESS_CONTEXT_KEYWORDS = [
        "address", "postcode", "post code", "first line", 
        "line of the address", "flat", "apartment", "line of your address"
    ]
    
    # Spoken numbers mapping
    SPOKEN_NUMBERS = {
        "ZERO": "0", "OH": "0", "ONE": "1", "TWO": "2", "THREE": "3",
        "FOUR": "4", "FIVE": "5", "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9",
        "TEN": "10", "ELEVEN": "11", "TWELVE": "12", "THIRTEEN": "13", "FOURTEEN": "14",
        "FIFTEEN": "15", "SIXTEEN": "16", "SEVENTEEN": "17", "EIGHTEEN": "18", "NINETEEN": "19",
        "TWENTY": "20", "THIRTY": "30", "FOURTY": "40", "FORTY": "40", "FIFTY": "50",
        "SIXTY": "60", "SEVENTY": "70", "EIGHTY": "80", "NINETY": "90"
    }
    
    def __init__(self):
        super().__init__(
            supported_entity="ADDRESS",
            supported_language="en",
            name="ContextAwareAddressRecognizer",
            context=self.ADDRESS_CONTEXT_KEYWORDS,
            deny_list=["__PLACEHOLDER__"]
        )
    
    def _contains_address_indicators(self, text: str) -> bool:
        """Check if text contains address-like components."""
        address_indicators = [
            'FLAT', 'APARTMENT', 'STREET', 'ROAD', 'AVENUE',
            'LANE', 'DRIVE', 'COURT', 'CLOSE', 'WAY', 'PLACE'
        ]
        return any(indicator in text for indicator in address_indicators)
    
    def _normalize_spoken_numbers(self, text: str) -> str:
        """Convert spoken numbers to digits."""
        text_upper = text.upper()
        for spoken, digit in sorted(self.SPOKEN_NUMBERS.items(), key=lambda x: -len(x[0])):
            text_upper = text_upper.replace(spoken, digit)
        return text_upper
    
    def analyze(self, text, entities, nlp_artifacts):
        """
        Detect address components with context awareness.
        Since main.py now passes full conversation context, we can check it properly.
        
        IMPORTANT: The 'text' parameter contains full conversation context from main.py.
        We should NOT apply exclude phrase checks to the full context, only check patterns.
        main.py will filter results to only redact entities in the current turn.
        """
        results = []
        text_upper = text.upper()
        
        # Check if conversation context (passed from main.py) mentions address
        # The 'text' parameter now includes previous turns from main.py
        has_address_context = any(keyword.upper() in text_upper for keyword in self.ADDRESS_CONTEXT_KEYWORDS)
        
        # Only redact customer responses that look like address components
        # Check if this text contains address indicators
        has_indicators = self._contains_address_indicators(text_upper)
        
        # DON'T check exclude phrases on full context - let main.py handle filtering by turn
        # The exclude check was preventing valid detections
        
        # Check if text mentions "ADDRESS IS" - strong signal for finding where address starts
        has_address_mention = "ADDRESS IS" in text_upper or "THE ADDRESS" in text_upper
        
        # If text looks like an address component (has numbers or address words)
        normalized = self._normalize_spoken_numbers(text_upper)
        has_numbers = bool(re.search(r'\d+', normalized))
        
        # Strategy: Find ALL occurrences of address-like patterns in the text
        # main.py will filter to only keep results in the current turn
        
        # Pattern 1: Text with address indicators (FLAT, APARTMENT, etc.)
        if has_indicators:
            # Find where the address indicators appear
            for indicator in ['FLAT', 'APARTMENT', 'NUMBER', 'STREET', 'ROAD', 'AVENUE',
                             'LANE', 'DRIVE', 'COURT', 'CLOSE', 'WAY', 'PLACE', 'MEASURE']:
                pattern = rf'\b{indicator}\b.*'
                for match in re.finditer(pattern, text_upper):
                    results.append(RecognizerResult(
                        entity_type="ADDRESS",
                        start=match.start(),
                        end=len(text),  # Redact from indicator to end
                        score=0.95,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="address_indicator",
                            pattern=indicator,
                            original_score=0.95
                        )
                    ))
                    break  # Only need one match
            if results:
                return results
        
        # Pattern 2: Text with "ADDRESS IS" followed by content
        if has_address_mention and has_numbers:
            # Find all occurrences of "ADDRESS IS" and redact everything after each one
            for address_is_match in re.finditer(r'\bADDRESS\s+IS\b', text_upper):
                # Find the start of the sentence/phrase containing "ADDRESS IS"
                # Look for beginning of sentence or "YES/NO/YEAH/SO" before it
                context_before = text_upper[:address_is_match.start()]
                sentence_start = address_is_match.start()
                
                # Try to find sentence boundaries
                last_period = context_before.rfind('.')
                last_question = context_before.rfind('?')
                last_boundary = max(last_period, last_question)
                
                if last_boundary > 0:
                    sentence_start = last_boundary + 1
                    # Skip whitespace
                    while sentence_start < len(text) and text[sentence_start].isspace():
                        sentence_start += 1
                else:
                    # No sentence boundary, check for common response starters
                    response_starters = [r'\bYES\b', r'\bNO\b', r'\bYEAH\b', r'\bSO\b', r'\bWELL\b']
                    for starter_pattern in response_starters:
                        starter_matches = list(re.finditer(starter_pattern, context_before))
                        if starter_matches:
                            # Use the last starter before "ADDRESS IS"
                            sentence_start = starter_matches[-1].start()
                            break
                
                results.append(RecognizerResult(
                    entity_type="ADDRESS",
                    start=sentence_start,
                    end=len(text),  # Redact to end of text
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="address_mention_full",
                        pattern="ADDRESS IS",
                        original_score=0.95
                    )
                ))
            if results:
                return results
        
        # Pattern 3: In address context, find number sequences that look like addresses
        if has_address_context and has_numbers:
            # Find sequences with numbers (potential address components)
            number_sequences = re.finditer(r'\b\d+[A-Z\s]*(?:\d+[A-Z\s]*)*\b', text_upper)
            for match in number_sequences:
                # Only match if appears to be address-like (not just a single digit)
                matched_text = match.group()
                if len(matched_text) > 1:  # More than just a single digit
                    results.append(RecognizerResult(
                        entity_type="ADDRESS",
                        start=match.start(),
                        end=match.end(),
                        score=0.85,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="address_number_sequence",
                            pattern="number_sequence",
                            original_score=0.85
                        )
                    ))
        
        return results


# -----------------------------------------------------------------------------
# 📮 5. UK Postcode Recognizer (with spoken format support)
# -----------------------------------------------------------------------------
class UKPostcodeRecognizer(PatternRecognizer):
    """
    Recognizes UK postcodes including spoken forms.
    """
    
    POSTCODE_CONTEXT_KEYWORDS = [
        "postcode", "post code", "postal code", "zip code"
    ]
    
    def __init__(self):
        super().__init__(
            supported_entity="UK_POSTCODE",
            supported_language="en",
            name="UKPostcodeRecognizer",
            context=self.POSTCODE_CONTEXT_KEYWORDS,
            deny_list=["__PLACEHOLDER__"]
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """
        Detect UK postcodes in various formats.
        """
        results = []
        text_upper = text.upper()
        
        # DON'T check conversation history - only check current turn
        # This prevents over-redaction of agent questions
        
        # Only redact if this turn looks like a postcode response
        # Exclude common phrases and agent questions
        exclude_phrases = ["ACCOUNT HOLDER", "YES SIR", "NO SIR", "YEAH", "TRADE AGREEMENT",
                          "POST CODE", "POSTCODE", "WHAT'S", "AND THE", "NAME IS", "PASSWORD IS", "MY NAME"]
        if any(phrase in text_upper for phrase in exclude_phrases):
            return results
        
        # Detect short responses that look like postcodes (mix of letters and numbers, < 10 words)
        if len(text.split()) <= 10:
            # Check if it has letters and numbers mixed (typical postcode pattern)
            has_letters = bool(re.search(r'[A-Z]', text_upper))
            has_numbers = bool(re.search(r'\d', text_upper))
            
            if has_letters and has_numbers:
                # Redact entire response
                results.append(RecognizerResult(
                    entity_type="UK_POSTCODE",
                    start=0,
                    end=len(text),
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="postcode_pattern",
                        pattern="context_based",
                        original_score=0.95
                    )
                ))
        
        return results


# -----------------------------------------------------------------------------
# 👤 6. Simplified Name Recognizer (relies on spaCy, minimal custom logic)
# -----------------------------------------------------------------------------
class SimplifiedNameRecognizer(PatternRecognizer):
    """
    Minimal custom name logic - mostly trusts spaCy NER.
    Only handles specific patterns like greetings and spelled names.
    No context keywords needed - full conversation context passed from main.py
    """
    
    def __init__(self):
        super().__init__(
            supported_entity="PERSON",
            supported_language="en",
            name="SimplifiedNameRecognizer",
            deny_list=["__PLACEHOLDER__"]
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """
        Minimal custom name detection - trust spaCy for most cases.
        Full conversation context is already provided from main.py
        """
        results = []
        text_upper = text.upper()
        
        # Pattern 1: Spelled-out names (e.g., "A P P L E" or "R O S E")
        spelled_pattern = r'\b([A-Z]\s+){2,}[A-Z]\b'
        for match in re.finditer(spelled_pattern, text_upper):
            spelled_text = match.group().replace(' ', '')
            if len(spelled_text) >= 3:
                results.append(RecognizerResult(
                    entity_type="PERSON",
                    start=match.start(),
                    end=match.end(),
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="spelled_name",
                        pattern=spelled_pattern,
                        original_score=0.95
                    )
                ))
        
        # Pattern 2: Names after "NAME IS" including titles
        name_intro_patterns = [
            r'NAME\s+IS\s+((?:MISSUS|MISTER|MR|MRS|MS|MISS)\s+[A-Z]{3,})',
            r'NAME\s+IS\s+([A-Z]{3,})',
            r'CALLED\s+((?:MISSUS|MISTER|MR|MRS|MS|MISS)\s+[A-Z]{3,})',
            r'CALLED\s+([A-Z]{3,})',
        ]
        
        for pattern in name_intro_patterns:
            for match in re.finditer(pattern, text_upper):
                name_text = match.group(1)
                if len(name_text) >= 3:
                    name_start = match.start(1)
                    name_end = match.end(1)
                    results.append(RecognizerResult(
                        entity_type="PERSON",
                        start=name_start,
                        end=name_end,
                        score=0.92,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="name_introduction",
                            pattern=pattern,
                            original_score=0.92
                        )
                    ))
        
        return results


# -----------------------------------------------------------------------------
# 🔐 7. Keep existing Password Recognizer (it works well)
# -----------------------------------------------------------------------------
from utils.customer_registry import AlphanumericPasswordRecognizer
