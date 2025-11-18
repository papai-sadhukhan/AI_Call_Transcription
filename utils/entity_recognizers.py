"""
STATEFUL ENTITY RECOGNIZERS (EntityRecognizer base class)
ALL recognizers use ConversationContextTracker for stateful detection.
NO context window concatenation - pure stateful approach.
"""
import re
import logging
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
        # Cache number_words for efficient reuse across recognizers
        self._number_words_list = None
        self._number_words_set = None
        self.reset()
    
    def get_number_words(self, as_set=False):
        """
        Get number words from config (cached for performance).
        
        Args:
            as_set: If True, return as set for fast lookup. If False, return as list.
        
        Returns:
            List or set of uppercase number words
        """
        if self._number_words_list is None:
            # Load once from config, cache for reuse
            self._number_words_list = self.context_indicators.get('number_words', [])
            if not self._number_words_list:
                logger = logging.getLogger("entity_redaction")
                logger.warning("number_words not found in config, using empty list. Number word detection may not work.")
            self._number_words_set = set(self._number_words_list)
        
        return self._number_words_set if as_set else self._number_words_list
    
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
        self.expecting_phone = False
    
    def update_context(self, text: str):
        """Update context based on current turn text (agent or customer)."""
        import logging
        self.reset()  # Reset on each turn
        self.last_turn_text = text.upper()
        
        # DEBUG: Log if we detect the combined pattern
        if "FULL NAME" in self.last_turn_text and "ADDRESS" in self.last_turn_text and "AIR CODE" in self.last_turn_text:
            logger = logging.getLogger("entity_redaction")
            logger.debug(f"CONTEXT TRACKER: Detected combined pattern in: {text[:80]}...")
        
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
        
        # DEBUG: Log flags if both are set
        if self.expecting_address and self.expecting_postcode:
            logger = logging.getLogger("entity_redaction")
            logger.debug(f"CONTEXT TRACKER: Set expecting_address=True AND expecting_postcode=True")
        
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
        
        # Phone number detection
        phone_indicators = self.context_indicators.get('phone_number', [])
        self.expecting_phone = any(
            indicator in self.last_turn_text for indicator in phone_indicators
        )
        
        # Phone number detection
        phone_indicators = self.context_indicators.get('phone_number', [])
        self.expecting_phone_number = any(
            indicator in self.last_turn_text for indicator in phone_indicators
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
        # Hardcoded score for all custom analyzers
        self.detection_score = 0.85
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
        # Get number words from shared config (as set for fast lookup)
        number_words = self.context_tracker.get_number_words(as_set=True)
        
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
                            score=self.detection_score,
                            analysis_explanation=AnalysisExplanation(
                                recognizer=self.__class__.__name__,
                                pattern_name="spelled_reference_number",
                                pattern="number_words_sequence",
                                original_score=self.detection_score
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
                score=self.detection_score,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="digit_reference_number",
                    pattern=digit_pattern,
                    original_score=self.detection_score
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
        # Hardcoded score for all custom analyzers
        self.detection_score = 0.85
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
                score=self.detection_score,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="double_digit",
                    pattern=double_pattern,
                    original_score=self.detection_score
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
                    score=self.detection_score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="context_based_bank_digits",
                        pattern=digit_pattern,
                        original_score=self.detection_score
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
        # Hardcoded score for all custom analyzers
        self.detection_score = 0.85
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
        # Build regex pattern from config number words
        number_words_list = self.context_tracker.get_number_words(as_set=False)
        # Use basic digits 0-9 for card numbers (not extended words like OH, DOUBLE)
        basic_numbers = [w for w in number_words_list if w in ['ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE']]
        number_words = r'(?:' + '|'.join(basic_numbers) + r'|\d)'
        four_digits_pattern = rf'\b{number_words}\s+{number_words}\s+{number_words}\s+{number_words}\b'
        
        for match in re.finditer(four_digits_pattern, text.upper()):
            results.append(RecognizerResult(
                entity_type="CREDIT_CARD",
                start=match.start(),
                end=match.end(),
                score=self.detection_score,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="four_card_digits",
                    pattern=four_digits_pattern,
                    original_score=self.detection_score
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
        #             score=0.85,
        #             analysis_explanation=AnalysisExplanation(
        #                 recognizer=self.__class__.__name__,
        #                 pattern_name="four_digit_number",
        #                 pattern=four_digit_number,
        #                 original_score=0.85
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
                    score=self.detection_score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="single_card_digit",
                        pattern=digit_pattern,
                        original_score=self.detection_score
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
        # Hardcoded score for all custom analyzers
        self.detection_score = 0.85
        super().__init__(
            supported_entities=["PERSON"],
            supported_language="en",
            name="StatefulNameRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect names in two modes:
        1. Agent self-introductions (unconditional): MY NAME IS X, I AM X, HERE IS X, THIS IS X
        2. Customer names (contextual): Only when expecting_name=True
        
        IMPORTANT: When BOTH address AND postcode are expected together, skip name detection
        and let AddressRecognizer handle the full response (name + address + postcode combined).
        """
        results = []
        text_upper = text.upper()
        
        # Skip name detection if both address AND postcode are expected
        # Let AddressRecognizer handle the combined response
        if self.context_tracker.expecting_address and self.context_tracker.expecting_postcode:
            return results
        
        words = text_upper.split()
        
        # Get conversational words from context_indicators (loaded from deny_list in YAML)
        # These are words that typically indicate the text is NOT a name
        conversational_words_list = self.context_indicators.get('conversational_words', [])
        if not conversational_words_list:
            logger = logging.getLogger("entity_redaction")
            logger.warning("conversational_words not found in config, name detection may not work correctly.")
        conversational_words = set(conversational_words_list) if conversational_words_list else set()
        
        # UNCONDITIONAL PATTERNS: Agent self-introductions (works without expecting_name)
        # ONLY use the most explicit pattern to avoid false positives
        # "MY NAME IS X" is the clearest indicator of name introduction
        
        # Common words that typically follow a name (boundary detection)
        # Load from config or use empty pattern
        name_boundaries_list = self.context_indicators.get('name_boundaries', [])
        if name_boundaries_list:
            # Escape special regex characters and join with |
            escaped_boundaries = [w.replace("'", "\\'") for w in name_boundaries_list]
            name_boundaries = r'(?:' + '|'.join(escaped_boundaries) + ')'
        else:
            logger = logging.getLogger("entity_redaction")
            logger.warning("name_boundaries not found in config, using minimal pattern.")
            name_boundaries = r'(?:$)'  # Match nothing
        
        agent_intro_patterns = [
            # MY NAME IS SHAUNA HOW... → captures only SHAUNA
            # MY NAME IS TERRY I'M... → captures only TERRY
            # MY NAME'S JOHN → captures JOHN
            # This is the ONLY reliable agent introduction pattern
            (rf'MY\s+NAME(?:\s+IS|\'S)\s+([A-Z]{{3,}})\b(?=\s+{name_boundaries}|\s*[,.]|\s*$)', 'agent_my_name_is'),
        ]
        
        # REMOVED: These patterns caused too many false positives:
        # - "I AM DOING" matched as "I AM [NAME]"
        # - "I'M FINE" matched as "I'M [NAME]"  
        # - "IT'S GOING" matched as "IT'S [NAME]"
        # 
        # Only "MY NAME IS X" is explicit enough to use without context
        
        for pattern, pattern_name in agent_intro_patterns:
            for match in re.finditer(pattern, text_upper):
                name_text = match.group(1)
                # Filter out common conversational words that might match
                name_words = name_text.split()
                non_conversational = [w for w in name_words if w not in conversational_words]
                
                # Only match if at least one word is non-conversational and 3+ chars
                if non_conversational and len(name_text) >= 3:
                    name_start = match.start(1)
                    name_end = match.end(1)
                    results.append(RecognizerResult(
                        entity_type="PERSON",
                        start=name_start,
                        end=name_end,
                        score=self.detection_score,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name=pattern_name,
                            pattern=pattern,
                            original_score=self.detection_score
                        )
                    ))
        
        # If agent intro patterns found, return immediately (don't need contextual patterns)
        if results:
            return results
        
        # CONTEXTUAL PATTERNS: Only detect if agent asked for customer's name
        if not self.context_tracker.expecting_name:
            return results
        
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
                        score=self.detection_score,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="spelled_name_full_response",
                            pattern="context_based_full_redaction",
                            original_score=self.detection_score
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
                    score=self.detection_score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="spelled_name",
                        pattern=spelled_pattern,
                        original_score=self.detection_score
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
                        score=self.detection_score,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="name_introduction",
                            pattern=pattern,
                            original_score=self.detection_score
                        )
                    ))
        
        # Pattern 4: Short direct name response (VERY RESTRICTIVE)
        # e.g., "JOHN SMITH" or "ROSEMARY" as direct answer when asked for name
        # This pattern is DISABLED by default due to high false positive rate
        # Common verbs (DOING, GOING, TALKING, etc.) get incorrectly matched
        # Better to rely on Patterns 1-3 which are more explicit
        # 
        # If needed, uncomment and add additional validation:
        # - Check against list of common English verbs/adjectives
        # - Use NLP POS tagging to verify it's a proper noun
        # - Require at least one capital letter in middle of word (like "McGregor")
        #
        # if not results and len(words) <= 2 and len(words) >= 1:
        #     all_caps_words = [w for w in words if w.isalpha() and len(w) >= 4]  # Min 4 chars
        #     conversational_count = sum(1 for w in words if w in conversational_words)
        #     
        #     if len(all_caps_words) == len(words) and conversational_count == 0:
        #         # Additional validation: check it's not a common verb/adjective
        #         common_verbs = {'DOING', 'GOING', 'TALKING', 'TRYING', 'WORKING', 'FINE', 'GOOD', 'GREAT'}
        #         potential_names = [w for w in words if w not in common_verbs]
        #         if len(potential_names) == len(words):
        #             results.append(RecognizerResult(...))
        
        # Pattern 5: Simple direct name response (when expecting name)
        # e.g., "CLEAR STANLEY DAVIS" or "JOHN SMITH" 
        # Strategy: When expecting a name, redact the entire response if it consists primarily of 
        # capitalized words (filtering out filler words)
        if not results:
            # Skip common filler words at start (load from config)
            filler_words_list = self.context_indicators.get('filler_words', [])
            filler_words = set(filler_words_list) if filler_words_list else set()
            
            # Additional validation: not a common verb/adjective/conversational word
            common_non_names = {
                'DOING', 'GOING', 'TALKING', 'TRYING', 'WORKING', 'LOOKING', 'CALLING',
                'FINE', 'GOOD', 'GREAT', 'OKAY', 'ALRIGHT', 'PERFECT', 'LOVELY',
                'CORRECT', 'RIGHT', 'WRONG', 'TRUE', 'FALSE', 'CLEAR'
            }
            # Merge conversational words with common_non_names for validation
            all_non_name_words = conversational_words.union(common_non_names)
            
            # Collect consecutive name words (alphabetic, 3+ chars, not in deny lists)
            name_words = []
            for word in words:
                if word in filler_words:
                    continue  # Skip filler at beginning
                elif word.isalpha() and len(word) >= 3 and word not in all_non_name_words:
                    name_words.append(word)
                elif name_words:  
                    # Stop if we've started collecting name words and hit a non-name word
                    break
            
            # If we found 1-3 consecutive name words, redact them all as a complete name
            if len(name_words) >= 1 and len(name_words) <= 3:
                # Find position of first and last name word in original text
                first_name_word = name_words[0]
                last_name_word = name_words[-1]
                
                word_start = text_upper.find(first_name_word)
                word_end = text_upper.find(last_name_word) + len(last_name_word)
                
                if word_start >= 0 and word_end > word_start:
                    results.append(RecognizerResult(
                        entity_type="PERSON",
                        start=word_start,
                        end=word_end,
                        score=self.detection_score,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            pattern_name="direct_name_response",
                            pattern="context_based_full_name",
                            original_score=self.detection_score
                        )
                    ))
        
        return results


class StatefulAddressRecognizer(EntityRecognizer):
    """
    Recognizes addresses when agent asked for address.
    SIMPLE LOGIC: When context indicates address expected, redact any alphanumeric sequence.
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        # Hardcoded score for all custom analyzers
        self.detection_score = 0.85
        super().__init__(
            supported_entities=["LOCATION"],
            supported_language="en",
            name="StatefulAddressRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """
        SIMPLIFIED ADDRESS DETECTION:
        1. Check if agent asked for address (context keywords: ADDRESS, STREET, POSTCODE, etc.)
        2. If yes, redact ANY response containing letters/numbers/words
        3. Skip only common filler words
        
        Example: "C FOUR SIX WEDNESDAY BILL" → redact as address
        
        COMBINED DETECTION:
        When agent asks for both address AND postcode together (e.g., "FULL ADDRESS WITH POSTCODE"),
        redact the entire response as it contains both PII elements.
        """
        logger = logging.getLogger("entity_redaction")
        logger.debug(f"AddressRecognizer.analyze called: expecting_address={self.context_tracker.expecting_address}, expecting_postcode={self.context_tracker.expecting_postcode}, text={text[:60] if text else 'EMPTY'}...")
        results = []
        text_upper = text.upper()
        
        # Only detect if agent asked for address in PREVIOUS turn
        if not self.context_tracker.expecting_address:
            return results
        
        # COMBINED ADDRESS + POSTCODE: When both are expected together, redact entire response
        # This handles cases like "DAMIEN O'BRIEN TWENTY WILL BOOK LAUNDRY BRIAN AND FORTY AND V FIVE EIGHT FIVE"
        # where the response contains name + address + postcode all together
        if self.context_tracker.expecting_address and self.context_tracker.expecting_postcode:
            # DEBUG
            logger.debug(f"AddressRecognizer: COMBINED detection branch HIT!")
            logger.debug(f"  Text: {text[:80]}...")
            logger.debug(f"  Stripped length: {len(text.strip())}")
            logger.debug(f"  expecting_address={self.context_tracker.expecting_address}, expecting_postcode={self.context_tracker.expecting_postcode}")
            
            # Redact entire response (it's all PII - name, address, and postcode combined)
            if len(text.strip()) > 0:
                logger.debug(f"  Creating LOCATION result...")
                results.append(RecognizerResult(
                    entity_type="LOCATION",
                    start=0,
                    end=len(text),
                    score=self.detection_score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="combined_address_postcode",
                        pattern="context_based_full_redaction",
                        original_score=self.detection_score
                    )
                ))
                logger.debug(f"  Returning {len(results)} results")
                return results
            else:
                logger.debug(f"  Text is empty, skipping")
        
        # Simple approach: If context expects address, check if response has alphanumeric content
        # Skip common filler words (load from config)
        words = text_upper.split()
        filler_words_list = self.context_indicators.get('filler_words', [])
        filler_words = set(filler_words_list) if filler_words_list else set()
        
        # Get number words from shared config
        number_words = self.context_tracker.get_number_words(as_set=True)
        
        # Extract significant content (alphanumeric words, single letters, number words)
        significant_content = []
        for word in words:
            if word in filler_words:
                continue
            # Include: alphanumeric words, single letters, number words
            if word.isalpha() or word.isdigit() or word in number_words:
                significant_content.append(word)
        
        # If response has significant alphanumeric content, redact it as address
        if len(significant_content) >= 2:  # At least 2 significant words/letters/numbers
            # SIMPLE: Redact from first to last significant word
            # Build the redaction text by finding positions properly
            first_word = significant_content[0]
            last_word = significant_content[-1]
            
            # Find actual positions in text by reconstructing
            start_idx = None
            end_idx = None
            
            # Find FIRST occurrence of first_word
            for i, word in enumerate(words):
                if word == first_word and start_idx is None:
                    start_idx = i
                    break
            
            # Find LAST occurrence of last_word (reverse iteration)
            for i in range(len(words) - 1, -1, -1):
                if words[i] == last_word:
                    end_idx = i
                    break
            
            if start_idx is not None and end_idx is not None:
                # Calculate character positions
                start_pos = len(' '.join(words[:start_idx]))
                if start_idx > 0:
                    start_pos += 1  # Add space before
                
                end_pos = len(' '.join(words[:end_idx + 1]))
                
                results.append(RecognizerResult(
                    entity_type="LOCATION",
                    start=start_pos,
                    end=end_pos,
                    score=self.detection_score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="simple_alphanumeric_sequence",
                        pattern="context_based_address",
                        original_score=self.detection_score
                    )
                ))
        
        return results


class StatefulPostcodeRecognizer(EntityRecognizer):
    """
    Recognizes UK postcodes when postcode context is present.
    SIMPLE LOGIC: When context indicates postcode expected, redact any letters + numbers.
    Uses ConversationContextTracker for stateful detection.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        # Hardcoded score for all custom analyzers
        self.detection_score = 0.85
        super().__init__(
            supported_entities=["UK_POSTCODE"],
            supported_language="en",
            name="StatefulPostcodeRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """
        SIMPLIFIED POSTCODE DETECTION:
        1. Check if agent asked for postcode (context keywords: POSTCODE, POST CODE, etc.)
        2. If yes, redact ANY letters and numbers in the response
        3. Skip only common filler words
        
        Example: "HD TWO FIVE C F" → redact as postcode
        """
        results = []
        text_upper = text.upper()
        words = text_upper.split()
        
        # Only detect when agent explicitly asked for postcode in previous turn
        if not self.context_tracker.expecting_postcode:
            return results
        
        # Simple approach: If context expects postcode, look for letters + numbers
        # Load filler words from config
        filler_words_list = self.context_indicators.get('filler_words', [])
        filler_words = set(filler_words_list) if filler_words_list else set()
        
        # Get number words from shared config
        number_words = self.context_tracker.get_number_words(as_set=True)
        
        # Extract significant content (letters, numbers, number words)
        significant_content = []
        for word in words:
            if word in filler_words:
                continue
            # Include: letters (especially short ones like postcode letters), number words, digits
            if word.isalpha() or word.isdigit() or word in number_words:
                significant_content.append(word)
        
        # If response has letters + numbers, redact as postcode
        has_letters = any(w.isalpha() and w not in number_words for w in significant_content)
        has_numbers = any(w.isdigit() or w in number_words for w in significant_content)
        
        if has_letters and has_numbers and len(significant_content) >= 2:
            # SIMPLE: Redact from first to last significant word
            first_word = significant_content[0]
            last_word = significant_content[-1]
            
            # Find actual positions in words list
            start_idx = None
            end_idx = None
            
            # Find FIRST occurrence of first_word
            for i, word in enumerate(words):
                if word == first_word and start_idx is None:
                    start_idx = i
                    break
            
            # Find LAST occurrence of last_word (reverse iteration)
            for i in range(len(words) - 1, -1, -1):
                if words[i] == last_word:
                    end_idx = i
                    break
            
            if start_idx is not None and end_idx is not None:
                # Calculate character positions
                start_pos = len(' '.join(words[:start_idx]))
                if start_idx > 0:
                    start_pos += 1  # Add space before
                
                end_pos = len(' '.join(words[:end_idx + 1]))
                
                results.append(RecognizerResult(
                    entity_type="UK_POSTCODE",
                    start=start_pos,
                    end=end_pos,
                    score=self.detection_score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="simple_letters_and_numbers",
                        pattern="context_based_postcode",
                        original_score=self.detection_score
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
        # Hardcoded score for all custom analyzers
        self.detection_score = 0.85
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
        
        # Simplified approach: When expecting email, detect anything with "AT" or "@" followed by "DOT"
        # This catches: "S DOT DAVIES AT J M U DOT AC DOT UK"
        # Pattern handles single letters and multi-letter words with DOT separators
        email_patterns = [
            # Pattern 1: Local part with DOTs (single letter or words), then AT, then domain with DOTs
            # Matches: "S DOT DAVIES AT J M U DOT AC DOT UK" or "NAME AT domain DOT com"
            r'[A-Z](?:\s+DOT\s+[A-Z]+)+\s+(?:AT|@)\s+[A-Z](?:\s+[A-Z])*(?:\s+DOT\s+[A-Z]+)+',
            # Pattern 2: Simple format without DOT in local part (e.g., "NAME AT domain DOT com")
            r'[A-Z]+\s+(?:AT|@)\s+[A-Z]+(?:\s+DOT\s+[A-Z]+)+',
            # Pattern 3: "FOR" variant (e.g., "S FOR AT domain DOT com")
            r'[A-Z]\s+FOR\s+(?:AT|@)\s+[A-Z]+(?:\s+DOT\s+[A-Z]+)+',
        ]
        
        for pattern in email_patterns:
            for match in re.finditer(pattern, text_upper):
                results.append(RecognizerResult(
                    entity_type="EMAIL_ADDRESS",
                    start=match.start(),
                    end=match.end(),
                    score=self.detection_score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="spoken_email_pattern",
                        pattern=pattern,
                        original_score=self.detection_score
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
        # Hardcoded score for all custom analyzers
        self.detection_score = 0.85
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
        
        # Get number words from shared config (as set for fast lookup)
        number_words = self.context_tracker.get_number_words(as_set=True)
        
        # Get conversational words from config (loaded from deny_list in YAML)
        # These words are already included in deny_list: WRITTEN, DOWN, SOMEWHERE, PASSWORD, LET, CHECK
        conversational_words_list = self.context_indicators.get('conversational_words', [])
        if not conversational_words_list:
            logger = logging.getLogger("entity_redaction")
            logger.warning("conversational_words not found in config, password detection may not work correctly.")
        conversational_words = set(conversational_words_list) if conversational_words_list else set()
        
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
                if consecutive_count >= 2:  # Minimum 2 elements for a password (handles short passwords)
                    break
                elif consecutive_count > 0 and consecutive_count < 2:
                    # Reset if we don't have enough elements yet
                    password_start_idx = -1
                    password_end_idx = -1
                    consecutive_count = 0
        
        # If we found a password sequence with at least 2 elements
        if consecutive_count >= 2 and password_start_idx != -1:
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
                score=self.detection_score,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="password_sequence_detection",
                    pattern="hybrid_context_pattern",
                    original_score=self.detection_score
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
                    score=self.detection_score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="short_password_response",
                        pattern="context_based_full_redaction",
                        original_score=self.detection_score
                    )
                ))
        
        return results


class StatefulPhoneNumberRecognizer(EntityRecognizer):
    """
    Simple phone number recognizer - detects sequences of 9+ spoken number words.
    Example: "ZERO DOUBLE SEVEN NINE FOUR FIVE OH FIVE EIGHT THREE SIX"
    """
    
    def __init__(self, context_tracker: ConversationContextTracker = None, context_indicators: Dict = None):
        self.context_tracker = context_tracker
        self.context_indicators = context_indicators or {}
        # Hardcoded score for all custom analyzers
        self.detection_score = 0.85
        super().__init__(
            supported_entities=["PHONE_NUMBER"],
            supported_language="en",
            name="StatefulPhoneNumberRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect phone numbers - simple pattern: 9+ consecutive spoken number words."""
        results = []
        text_upper = text.upper()
        
        # Get number words from shared config (includes OH, DOUBLE, TRIPLE for phone numbers)
        number_words = self.context_tracker.get_number_words(as_set=False)
        
        # Pattern: 9+ consecutive number words (UK phone = 10-11 digits, so 9+ words is safe)
        # Example: "ZERO DOUBLE SEVEN NINE FOUR FIVE OH FIVE EIGHT THREE SIX"
        number_word_pattern = r'\b(?:' + '|'.join(number_words) + r')(?:\s+(?:' + '|'.join(number_words) + r')){8,}\b'
        
        for match in re.finditer(number_word_pattern, text_upper):
            results.append(RecognizerResult(
                entity_type="PHONE_NUMBER",
                start=match.start(),
                end=match.end(),
                score=self.detection_score,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="spoken_phone_number",
                    pattern="nine_plus_number_words",
                    original_score=self.detection_score
                )
            ))
        
        # Also match pure digit sequences (10-11 digits)
        digit_pattern = r'\b0\d{9,10}\b'
        for match in re.finditer(digit_pattern, text):
            results.append(RecognizerResult(
                entity_type="PHONE_NUMBER",
                start=match.start(),
                end=match.end(),
                score=self.detection_score,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    pattern_name="digit_phone_number",
                    pattern=digit_pattern,
                    original_score=self.detection_score
                )
            ))
        
        return results
