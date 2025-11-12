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
        
        # Get conversational words from context_indicators (loaded from deny_list in YAML)
        # These are words that typically indicate the text is NOT a name
        conversational_words_list = self.context_indicators.get('conversational_words', [])
        conversational_words = set(conversational_words_list) if conversational_words_list else set([
            'THE', 'IS', 'IT', 'WITH', 'YOU', 'YOUR', "YOU'RE", 'I', 'A', 'AN', 'TO', 'OF'
        ])
        
        # Check if response is primarily single letters (spelled-out name like "G R A C E")
        # or contains word(s) followed by spelled letters
        single_letters = [w for w in words if len(w) == 1 and w.isalpha()]
        
        # Filter out single letters that are common words (I, A)
        meaningful_single_letters = [w for w in single_letters if w not in conversational_words]
        
        # Pattern 1: Response with spelled-out name (e.g., "GREY G R A C E" or just "G R A C E")
        # If we have 3+ meaningful single letters AND they're consecutive, likely entire response is the name
        if len(meaningful_single_letters) >= 3:
            # Check if single letters form a consecutive sequence
            single_letter_indices = [i for i, w in enumerate(words) if len(w) == 1 and w.isalpha() and w not in conversational_words]
            
            # Check for consecutive sequence (allowing up to 2 word gaps for names like "GREY G R A C E")
            if len(single_letter_indices) >= 3:
                is_consecutive = True
                max_gap = 2
                for i in range(len(single_letter_indices) - 1):
                    if single_letter_indices[i+1] - single_letter_indices[i] > max_gap:
                        is_consecutive = False
                        break
                
                if is_consecutive:
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
        # Look for sequences of 3+ single letters separated by spaces
        spelled_pattern = r'\b([A-Z]\s+){2,}[A-Z]\b'
        for match in re.finditer(spelled_pattern, text_upper):
            matched_text = match.group()
            spelled_letters = [w for w in matched_text.split() if len(w) == 1]
            
            # Check if letters are not conversational words
            non_conversational = [l for l in spelled_letters if l not in conversational_words]
            
            if len(non_conversational) >= 3:
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
        # BUT exclude responses with many conversational words
        if not results and len(words) <= 3 and len(words) >= 1:
            # Check if all words are capitalized and at least 3 chars
            all_caps_words = [w for w in words if w.isalpha() and len(w) >= 3]
            conversational_count = sum(1 for w in words if w in conversational_words)
            
            # Only match if:
            # 1. All words are alphabetic and 3+ chars
            # 2. No more than 1 conversational word (allows for "YES JOHN" but not "YOU'RE CAN'T")
            if len(all_caps_words) == len(words) and conversational_count <= 1:
                # Additional check: at least one word should look like a proper name (capitalized, uncommon)
                potential_names = [w for w in words if w not in conversational_words and len(w) >= 3]
                if len(potential_names) >= 1:
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
        """
        Simplified postcode detection logic:
        1. Check if postcode was mentioned in previous turn
        2. If yes, check if response contains single letters AND (number words OR digits)
        3. If yes, redact the entire response as postcode
        
        Example: "ER SEVEN SIX Q T" has letters (ER, Q, T) and numbers (SEVEN, SIX) -> redact
        """
        results = []
        text_upper = text.upper()
        words = text_upper.split()
        
        # Step 1: Check if postcode context exists from PREVIOUS turn
        # Only detect when agent explicitly asked for postcode in previous turn
        if not self.context_tracker.expecting_postcode:
            return results
        
        # Step 2: Check if response contains actual letter components (single letters or short letter sequences)
        # UK postcodes have letter parts like: ER, E, AB, Q, T, CD, etc.
        # Look for words that are 1-2 letters long (not number words)
        number_words = {'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE', 'ZERO', 
                       'TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN', 
                       'SEVENTEEN', 'EIGHTEEN', 'NINETEEN', 'TWENTY', 'THIRTY', 'FORTY', 'FIFTY',
                       'SIXTY', 'SEVENTY', 'EIGHTY', 'NINETY', 'HUNDRED'}
        
        # Find letter components (1-2 letter words that aren't number words)
        letter_components = [w for w in words if w.isalpha() and len(w) <= 2 and w not in number_words]
        has_letters = len(letter_components) > 0
        
        # Step 3: Check if response contains numbers (spoken number words OR digits)
        has_number_words = any(w in number_words for w in words)
        has_digits = bool(re.search(r'\d', text_upper))
        has_numbers = has_number_words or has_digits
        
        # Step 4: If response has both letter components and numbers, treat entire response as postcode
        if has_letters and has_numbers:
            results.append(RecognizerResult(
                entity_type="UK_POSTCODE",
                start=0,
                end=len(text),
                score=0.95,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="postcode_context_based",
                    pattern="letters_and_numbers_after_postcode_request",
                    original_score=0.95
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
        
        words = text_upper.split()
        
        # Get number words from config
        number_words = set(self.context_indicators.get('number_words', [
            'ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE',
            'TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN', 'SIXTEEN', 
            'SEVENTEEN', 'EIGHTEEN', 'NINETEEN', 'TWENTY', 'THIRTY', 'FORTY', 'FIFTY',
            'SIXTY', 'SEVENTY', 'EIGHTY', 'NINETY', 'HUNDRED'
        ]))
        
        # Get conversational words from config (loaded from deny_list in YAML)
        # These words are already included in deny_list: WRITTEN, DOWN, SOMEWHERE, PASSWORD, LET, CHECK
        conversational_words_list = self.context_indicators.get('conversational_words', [])
        conversational_words = set(conversational_words_list) if conversational_words_list else set([
            'THE', 'IS', 'IT', 'WITH', 'PASSWORD', 'WRITTEN', 'DOWN', 'SOMEWHERE'
        ])
        
        # Strategy: Find continuous sequences of single letters, number words, or digits
        # that don't include conversational words
        
        password_start_idx = -1
        password_end_idx = -1
        consecutive_count = 0
        
        for i, word in enumerate(words):
            # Check if word is a password component
            is_single_letter = (len(word) == 1 and word.isalpha())
            is_number_word = (word in number_words)
            is_digit = word.isdigit()
            is_conversational = (word in conversational_words)
            
            # If it's a password component and not a conversational word
            if (is_single_letter or is_number_word or is_digit) and not is_conversational:
                if password_start_idx == -1:
                    password_start_idx = i
                password_end_idx = i
                consecutive_count += 1
            else:
                # If we hit a conversational word and have accumulated password elements
                # Check if we should end the password sequence
                if consecutive_count >= 6:  # Minimum 6 elements for a password
                    break
                elif consecutive_count > 0 and consecutive_count < 6:
                    # Reset if we don't have enough elements yet
                    password_start_idx = -1
                    password_end_idx = -1
                    consecutive_count = 0
        
        # If we found a password sequence with at least 6 elements
        if consecutive_count >= 6 and password_start_idx != -1:
            # Calculate character positions in original text
            # Find the start position of the first password word
            text_position = 0
            for i, word in enumerate(words):
                if i == password_start_idx:
                    start_pos = text_position
                    break
                text_position += len(word) + 1  # +1 for space
            
            # Find the end position of the last password word
            text_position = 0
            for i, word in enumerate(words):
                text_position += len(word)
                if i == password_end_idx:
                    end_pos = text_position
                    break
                text_position += 1  # space
            
            # Find actual positions in original text (case-insensitive)
            # We need to map back to the original text preserving case
            start_char = len(' '.join(words[:password_start_idx]))
            if password_start_idx > 0:
                start_char += 1  # Add space before
            
            end_char = len(' '.join(words[:password_end_idx + 1]))
            
            results.append(RecognizerResult(
                entity_type="PASSWORD",
                start=start_char,
                end=end_char,
                score=0.95,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="password_sequence_detection",
                    pattern="hybrid_context_pattern",
                    original_score=0.95
                )
            ))
        
        # Fallback: If no specific sequence found but response is short and has alphanumeric
        # (direct password response with no prefix)
        elif not results and len(words) <= 15:
            has_letters = any(len(w) == 1 and w.isalpha() for w in words)
            has_numbers = any(w in number_words or w.isdigit() for w in words)
            non_conversational = sum(1 for w in words if w not in conversational_words)
            
            # If most words are password-like (not conversational) and has alphanumeric mix
            if has_letters and has_numbers and non_conversational >= len(words) * 0.6:
                results.append(RecognizerResult(
                    entity_type="PASSWORD",
                    start=0,
                    end=len(text),
                    score=0.90,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="short_password_response",
                        pattern="context_based_full_redaction",
                        original_score=0.90
                    )
                ))
        
        return results
