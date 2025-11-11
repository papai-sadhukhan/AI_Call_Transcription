"""
STATEFUL ENTITY RECOGNIZERS (EntityRecognizer base class)
ALL recognizers use ConversationContextTracker for stateful detection.
NO context window concatenation - pure stateful approach.
"""
import re
from typing import List, Optional, Dict
from presidio_analyzer import EntityRecognizer, RecognizerResult, AnalysisExplanation


class ConversationContextTracker:
    """
    Tracks conversation context for current turn only.
    Resets on each turn to maintain turn-level context.
    """
    
    def __init__(self, context_indicators: Dict = None):
        """
        Initialize with context indicators from config.
        
        Args:
            context_indicators: Dictionary containing context words/phrases for each entity type
        """
        self.context_indicators = context_indicators or {}
        self.reset()
    
    def reset(self):
        """Reset tracker for each new turn."""
        self.last_turn_text = ""
        self.expecting_reference_number = False
        self.expecting_bank_digits = False
        self.expecting_card_digits = False
        self.expecting_name = False
        self.expecting_address = False
        self.expecting_postcode = False
        self.expecting_email = False
        self.expecting_password = False
    
    def update_context(self, text: str):
        """Update context based on current turn text (agent or customer)."""
        self.reset()  # Reset on each turn
        self.last_turn_text = text.upper()
        
        # Reference number detection
        reference_indicators = self.context_indicators.get('reference_number', [])
        self.expecting_reference_number = any(
            indicator in self.last_turn_text for indicator in reference_indicators
        )
        
        # Bank digits detection
        bank_indicators = self.context_indicators.get('bank_digits', [])
        self.expecting_bank_digits = any(
            indicator in self.last_turn_text for indicator in bank_indicators
        )
        
        # Card digits detection (credit/debit card last 4 digits)
        card_indicators = self.context_indicators.get('card_digits', [])
        self.expecting_card_digits = any(
            indicator in self.last_turn_text for indicator in card_indicators
        )
        
        # Name detection
        name_indicators = self.context_indicators.get('name', [])
        self.expecting_name = any(
            indicator in self.last_turn_text for indicator in name_indicators
        )
        
        # Address detection
        address_indicators = self.context_indicators.get('address', [])
        self.expecting_address = any(
            indicator in self.last_turn_text for indicator in address_indicators
        )
        
        # Postcode detection
        postcode_indicators = self.context_indicators.get('postcode', [])
        self.expecting_postcode = any(
            indicator in self.last_turn_text for indicator in postcode_indicators
        )
        
        # Email detection
        email_indicators = self.context_indicators.get('email', [])
        self.expecting_email = any(
            indicator in self.last_turn_text for indicator in email_indicators
        )
        
        # Password detection
        password_indicators = self.context_indicators.get('password', [])
        self.expecting_password = any(
            indicator in self.last_turn_text for indicator in password_indicators
        )


class StatefulReferenceNumberRecognizer(EntityRecognizer):
    """
    Recognizes reference numbers when mentioned in conversation.
    Example: "YEAH ONE NINE ONE TWO ONE TWO EIGHT THAT'S THE SKY FAMILY"
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        super().__init__(
            supported_entities=["REFERENCE_NUMBER"],
            supported_language="en",
            name="StatefulReferenceNumberRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect reference numbers when context mentions reference number."""
        results = []
        text_upper = text.upper()
        
        # Only detect if context mentions reference number
        if not self.context_tracker.expecting_reference_number:
            return results
        
        # Pattern 1: Spelled-out numbers (e.g., "ONE NINE ONE TWO ONE TWO EIGHT")
        # Look for sequences of number words
        number_words = self.context_indicators.get('number_words', [
            'ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE',
            'TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN', 
            'SEVENTEEN', 'EIGHTEEN', 'NINETEEN', 'TWENTY'
        ])
        
        # Find sequences of number words (at least 5 for reference numbers)
        words = text_upper.split()
        i = 0
        while i < len(words):
            if words[i] in number_words:
                start_idx = i
                count = 0
                while i < len(words) and words[i] in number_words:
                    count += 1
                    i += 1
                
                # If we found at least 5 number words, it's likely a reference number
                if count >= 5:
                    # Find the text span
                    start_pos = text_upper.find(' '.join(words[start_idx:start_idx+count]))
                    if start_pos >= 0:
                        end_pos = start_pos + len(' '.join(words[start_idx:start_idx+count]))
                        results.append(RecognizerResult(
                            entity_type="REFERENCE_NUMBER",
                            start=start_pos,
                            end=end_pos,
                            score=0.95,
                            analysis_explanation=AnalysisExplanation(
                                recognizer=self.__class__.__name__,
                                pattern_name="spelled_reference_number",
                                pattern="number_words_sequence",
                                original_score=0.95
                            )
                        ))
            else:
                i += 1
        
        # Pattern 2: Digit sequences (7+ digits)
        digit_pattern = r'\b\d{7,}\b'
        for match in re.finditer(digit_pattern, text):
            results.append(RecognizerResult(
                entity_type="REFERENCE_NUMBER",
                start=match.start(),
                end=match.end(),
                score=0.90,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="digit_reference_number",
                    pattern=digit_pattern,
                    original_score=0.90
                )
            ))
        
        return results


class StatefulBankDigitsRecognizer(EntityRecognizer):
    """
    Recognizes bank digits only when agent asked for them.
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        super().__init__(
            supported_entities=["BANK_ACCOUNT_LAST_DIGITS"],
            supported_language="en",
            name="StatefulBankDigitsRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect bank digits only if we're expecting them."""
        results = []
        
        # Only detect if agent just asked for bank digits
        if not self.context_tracker.expecting_bank_digits:
            return results
        
        # Pattern 1: "DOUBLE" + digit
        double_pattern = r'\bDOUBLE\s+\d\b'
        for match in re.finditer(double_pattern, text, re.IGNORECASE):
            results.append(RecognizerResult(
                entity_type="BANK_ACCOUNT_LAST_DIGITS",
                start=match.start(),
                end=match.end(),
                score=0.95,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="double_digit",
                    pattern=double_pattern,
                    original_score=0.95
                )
            ))
        
        # Pattern 2: Any other digits (1 or 2 digits)
        digit_pattern = r'\b\d{1,2}\b'
        for match in re.finditer(digit_pattern, text):
            already_matched = any(r.start <= match.start() < r.end for r in results)
            if not already_matched:
                results.append(RecognizerResult(
                    entity_type="BANK_ACCOUNT_LAST_DIGITS",
                    start=match.start(),
                    end=match.end(),
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="context_based_bank_digits",
                        pattern=digit_pattern,
                        original_score=0.95
                    )
                ))
        
        return results


class StatefulCardDigitsRecognizer(EntityRecognizer):
    """
    Recognizes credit/debit card last 4 digits only when agent asked for them.
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        super().__init__(
            supported_entities=["CREDIT_CARD"],
            supported_language="en",
            name="StatefulCardDigitsRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect card digits only if we're expecting them."""
        results = []
        
        # Only detect if agent just asked for card digits
        if not self.context_tracker.expecting_card_digits:
            return results
        
        # Pattern 1: Four separate digits or number words (e.g., "NINE ZERO THREE FOUR" or "9 0 3 4")
        # Look for sequences of 4 single digits/number words
        number_words = r'(?:ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|\d)'
        four_digits_pattern = rf'\b{number_words}\s+{number_words}\s+{number_words}\s+{number_words}\b'
        
        for match in re.finditer(four_digits_pattern, text.upper()):
            results.append(RecognizerResult(
                entity_type="CREDIT_CARD",
                start=match.start(),
                end=match.end(),
                score=0.95,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="four_card_digits",
                    pattern=four_digits_pattern,
                    original_score=0.95
                )
            ))
        
        # Pattern 2: Four-digit number (e.g., "9034")
        # Commented out - only spelled-out digits observed in data
        # if not results:
        #     four_digit_number = r'\b\d{4}\b'
        #     for match in re.finditer(four_digit_number, text):
        #         results.append(RecognizerResult(
        #             entity_type="CREDIT_CARD",
        #             start=match.start(),
        #             end=match.end(),
        #             score=0.95,
        #             analysis_explanation=AnalysisExplanation(
        #                 recognizer=self.__class__.__name__,
        #                 pattern_name="four_digit_number",
        #                 pattern=four_digit_number,
        #                 original_score=0.95
        #             )
        #         ))
        
        # Pattern 3: Any single digits in the response (fallback)
        if not results:
            digit_pattern = r'\b\d\b'
            for match in re.finditer(digit_pattern, text):
                results.append(RecognizerResult(
                    entity_type="CREDIT_CARD",
                    start=match.start(),
                    end=match.end(),
                    score=0.90,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="single_card_digit",
                        pattern=digit_pattern,
                        original_score=0.90
                    )
                ))
        
        return results


class StatefulNameRecognizer(EntityRecognizer):
    """
    Recognizes names with pattern matching when agent asked for name.
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        super().__init__(
            supported_entities=["PERSON"],
            supported_language="en",
            name="StatefulNameRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect names only if we're expecting them."""
        results = []
        text_upper = text.upper()
        
        # Only detect if agent asked for name
        if not self.context_tracker.expecting_name:
            return results
        
        words = text_upper.split()
        
        # Check if response is primarily single letters (spelled-out name like "G R A C E")
        # or contains word(s) followed by spelled letters
        single_letters = [w for w in words if len(w) == 1 and w.isalpha()]
        
        # Pattern 1: Response with spelled-out name (e.g., "GREY G R A C E" or just "G R A C E")
        # If we have 3+ single letters in response, likely entire response is the name
        if len(single_letters) >= 3:
            # Redact entire response as it's the name being spelled out
            results.append(RecognizerResult(
                entity_type="PERSON",
                start=0,
                end=len(text),
                score=0.95,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="spelled_name_full_response",
                    pattern="context_based_full_redaction",
                    original_score=0.95
                )
            ))
            return results
        
        # Pattern 2: Spelled-out names within text (e.g., "MY NAME IS J O H N SMITH")
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
        
        # Pattern 3: Names after "NAME IS" or "CALLED"
        name_intro_patterns = [
            r'NAME\s+IS\s+((?:MISSUS|MISTER|MR|MRS|MS|MISS)\s+[A-Z]{3,})',
            r'NAME\s+IS\s+([A-Z]{3,}(?:\s+[A-Z]{3,})?)',
            r'CALLED\s+((?:MISSUS|MISTER|MR|MRS|MS|MISS)\s+[A-Z]{3,})',
            r'CALLED\s+([A-Z]{3,}(?:\s+[A-Z]{3,})?)',
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
        
        # Pattern 4: If short response with all caps words (likely a name as direct answer)
        # e.g., "JOHN SMITH" or "SMITH" as a direct response
        if not results and len(words) <= 3 and len(words) >= 1:
            # Check if all words are capitalized and at least 3 chars
            all_caps_words = [w for w in words if w.isalpha() and len(w) >= 3]
            if len(all_caps_words) == len(words):
                # Likely a name given as direct answer
                results.append(RecognizerResult(
                    entity_type="PERSON",
                    start=0,
                    end=len(text),
                    score=0.88,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="direct_name_response",
                        pattern="context_based_full_redaction",
                        original_score=0.88
                    )
                ))
        
        return results


class StatefulAddressRecognizer(EntityRecognizer):
    """
    Recognizes addresses when agent asked for address.
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        super().__init__(
            supported_entities=["ADDRESS"],
            supported_language="en",
            name="StatefulAddressRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect addresses only if we're expecting them."""
        results = []
        text_upper = text.upper()
        
        # Only detect if agent asked for address in PREVIOUS turn
        # Do NOT auto-detect just because customer mentions word "address"
        if not self.context_tracker.expecting_address:
            return results
        
        # Pattern 1: Traditional numeric addresses (e.g., "2 MILTON DRIVE")
        address_patterns = [
            r'\b\d{1,4}\s+[A-Z]+(?:\s+[A-Z]+)*\s+(?:[A-Z]\s+){1,2}(?:\d+\s+)?[A-Z](?:\s+[A-Z])?\b',
            r'\b\d{1,4}\s+[A-Z]+(?:\s+[A-Z]+){1,5}\b'
        ]
        
        street_indicators = self.context_indicators.get('street_indicators', [
            'STREET', 'ROAD', 'AVENUE', 'LANE', 'DRIVE', 'WAY', 'CLOSE', 'COURT', 'PLACE', 'SQUARE', 'GARDENS'
        ])
        
        for pattern in address_patterns:
            for match in re.finditer(pattern, text_upper):
                matched_text = match.group()
                has_street_word = any(word in matched_text for word in street_indicators)
                
                # Detect if it looks like address
                if has_street_word or len(matched_text.split()) >= 3:
                    results.append(RecognizerResult(
                        entity_type="ADDRESS",
                        start=match.start(),
                        end=match.end(),
                        score=0.95,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="address_line",
                            pattern=pattern,
                            original_score=0.95
                        )
                    ))
        
        # Pattern 2: Spelled-out addresses (e.g., "NUMBER TWO MILTON DRIVE")
        # Look for: "NUMBER" + number word + street name + street type
        number_words = self.context_indicators.get('number_words', [
            'ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE',
            'TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN', 
            'SEVENTEEN', 'EIGHTEEN', 'NINETEEN', 'TWENTY', 'THIRTY', 'FORTY', 'FIFTY',
            'SIXTY', 'SEVENTY', 'EIGHTY', 'NINETY', 'HUNDRED'
        ])
        
        # Pattern: "NUMBER" + number_word + street_name + street_type
        spelled_pattern = r'\bNUMBER\s+(?:' + '|'.join(number_words) + r')\s+[A-Z]+(?:\s+[A-Z]+)*?\s+(?:' + '|'.join(street_indicators) + r')\b'
        
        for match in re.finditer(spelled_pattern, text_upper):
            results.append(RecognizerResult(
                entity_type="ADDRESS",
                start=match.start(),
                end=match.end(),
                score=0.95,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="spelled_address",
                    pattern=spelled_pattern,
                    original_score=0.95
                )
            ))
        
        return results


class StatefulPostcodeRecognizer(EntityRecognizer):
    """
    Recognizes UK postcodes when postcode context is present.
    Handles both spelled-out (ONE THREE NINE H H) and standard formats.
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        super().__init__(
            supported_entities=["UK_POSTCODE"],
            supported_language="en",
            name="StatefulPostcodeRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect postcodes when context mentions postcode."""
        results = []
        text_upper = text.upper()
        
        # Check if postcode context is present from PREVIOUS turn OR current turn mentions it
        expecting_postcode_from_previous = self.context_tracker.expecting_postcode
        current_turn_mentions_postcode = (
            "POSTCODE" in text_upper or 
            "POST CODE" in text_upper or 
            "POSTAL CODE" in text_upper
        )
        
        # Only detect if postcode context is present (from either previous or current turn)
        if not (expecting_postcode_from_previous or current_turn_mentions_postcode):
            return results
        
        # Pattern 1: Spelled-out postcode with letters and numbers
        # Examples: "ONE THREE NINE H H", "A B I ONE THREE NINE H S FOR SUGAR"
        # Look for: letter(s) + number(s) + letter(s) pattern (typical UK postcode)
        
        # Strategy 1: Try to find postcode after "POST CODE" or "POSTCODE" keywords
        postcode_keywords = [r'POST\s*CODE\s+(?:IS\s+|WILL\s+HAVE\s+|YOU\s+WILL\s+HAVE\s+)?(.{10,50}?)(?:\s+FOR\s+|\s+AND\s+|$)',
                            r'POSTCODE\s+(?:IS\s+|WILL\s+HAVE\s+|YOU\s+WILL\s+HAVE\s+)?(.{10,50}?)(?:\s+FOR\s+|\s+AND\s+|$)']
        
        for keyword_pattern in postcode_keywords:
            for match in re.finditer(keyword_pattern, text_upper):
                postcode_candidate = match.group(1).strip()
                
                # Check if candidate has letter + number + letter pattern (UK postcode structure)
                has_letters = bool(re.search(r'[A-Z]', postcode_candidate))
                has_numbers = bool(re.search(r'(ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|ZERO|\d)', postcode_candidate))
                
                if has_letters and has_numbers:
                    # Calculate actual position in original text
                    postcode_start = match.start(1)
                    postcode_end = match.end(1)
                    
                    results.append(RecognizerResult(
                        entity_type="UK_POSTCODE",
                        start=postcode_start,
                        end=postcode_end,
                        score=0.95,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="postcode_after_keyword",
                            pattern=keyword_pattern,
                            original_score=0.95
                        )
                    ))
        
        # Strategy 2: General pattern for spelled-out postcodes
        # More flexible pattern to match various UK postcode formats when spelled out
        # Can have 1-4 letters, then 1-4 number words/digits, then 1-3 letters
        # Match sequences like: "A B I ONE THREE NINE H S" or "ONE THREE NINE H H"
        if not results:  # Only if keyword-based search didn't find anything
            postcode_pattern = r'\b(?:[A-Z]\s+){1,4}(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|ZERO|\d+\s+){1,4}(?:[A-Z]\s*){1,3}\b'
            
            for match in re.finditer(postcode_pattern, text_upper):
                matched_text = match.group()
                # Check if it contains both letters and numbers/number words
                has_letters = bool(re.search(r'[A-Z]', matched_text))
                has_numbers = bool(re.search(r'(ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|ZERO|\d)', matched_text))
                
                if has_letters and has_numbers:
                    results.append(RecognizerResult(
                        entity_type="UK_POSTCODE",
                        start=match.start(),
                        end=match.end(),
                        score=0.95,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="spelled_postcode",
                            pattern=postcode_pattern,
                            original_score=0.95
                        )
                    ))
        
        # Pattern 2: Mixed letters and numbers in short response
        # For responses with alphanumeric postcodes (e.g., spoken postcodes)
        if not results:  # Only if we haven't found spelled-out postcodes
            has_letters = bool(re.search(r'[A-Z]', text_upper))
            has_numbers = bool(re.search(r'\d', text_upper))
            
            if has_letters and has_numbers and len(text.split()) <= 15:
                # Redact entire response as it's likely a postcode
                results.append(RecognizerResult(
                    entity_type="UK_POSTCODE",
                    start=0,
                    end=len(text),
                    score=0.85,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="postcode_full_response",
                        pattern="context_based",
                        original_score=0.85
                    )
                ))
        
        return results


class StatefulEmailRecognizer(EntityRecognizer):
    """
    Recognizes spoken email addresses when agent asked for email.
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        super().__init__(
            supported_entities=["EMAIL_ADDRESS"],
            supported_language="en",
            name="StatefulEmailRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect emails only if we're expecting them."""
        results = []
        text_upper = text.upper()
        
        # Only detect if agent asked for email
        if not self.context_tracker.expecting_email:
            return results
        
        # Patterns for spoken email
        email_patterns = [
            r'\b[A-Z]+(?:\s+[A-Z]+)?\s+(?:AT|@)\s+[A-Z]+(?:\s+DOT\s+[A-Z]+)+\b',
            r'\b[A-Z]+\s+FOR\s+AT\s+[A-Z]+(?:\s+DOT\s+[A-Z]+)+\b',
        ]
        
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


class StatefulPasswordRecognizer(EntityRecognizer):
    """
    Recognizes alphanumeric passwords when agent asked for password.
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        super().__init__(
            supported_entities=["PASSWORD"],
            supported_language="en",
            name="StatefulPasswordRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect passwords only if we're expecting them."""
        results = []
        text_upper = text.upper()
        
        # Only detect if agent asked for password
        if not self.context_tracker.expecting_password:
            return results
        
        # Strategy: Check if response contains alphanumeric password pattern
        # Look for sequences with both letters and numbers/number words
        words = text_upper.split()
        
        # Check if text contains both letters and numbers/number words
        has_letters = bool(re.search(r'\b[A-Z]\b', text_upper))
        has_numbers = bool(re.search(r'\b(?:' + '|'.join(self.context_indicators.get('number_words', [
            'ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE'
        ])) + r'|\d+)\b', text_upper))
        
        # If the response contains alphanumeric content (letters + numbers), redact entire response
        # This handles cases like "THREE THREE TWO C D C Q I J SEVEN SIX EIGHT E"
        if has_letters and has_numbers and len(words) >= 4:
            # Redact the entire response as it's likely a password
            results.append(RecognizerResult(
                entity_type="PASSWORD",
                start=0,
                end=len(text),
                score=0.95,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="alphanumeric_password_full_response",
                    pattern="context_based_full_redaction",
                    original_score=0.95
                )
            ))
        elif has_letters and len(words) >= 6:
            # If just letters but long sequence, likely a password too
            results.append(RecognizerResult(
                entity_type="PASSWORD",
                start=0,
                end=len(text),
                score=0.90,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="letter_password_full_response",
                    pattern="context_based_full_redaction",
                    original_score=0.90
                )
            ))
        
        return results
