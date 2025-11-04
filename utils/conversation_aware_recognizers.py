"""
Conversation-aware PII recognizers that track context across turns.
This solves issues where customer answers need context from previous agent questions.
"""
import re
from typing import List, Optional, Dict
from presidio_analyzer import EntityRecognizer, RecognizerResult, AnalysisExplanation


class ConversationContextTracker:
    """
    Tracks conversation context to understand when customer is answering specific questions.
    """
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset tracker for a new conversation."""
        self.last_agent_turn = ""
        self.expecting = {
            "bank_digits": False,
            "postcode": False,
            "full_name": False,
            "address": False,
            "email": False
        }
    
    def update_from_agent(self, text: str):
        """Update context based on agent's question."""
        self.last_agent_turn = text.upper()
        
        # Reset expectations
        for key in self.expecting:
            self.expecting[key] = False
        
        # Detect what agent is asking for
        if "LAST TWO DIGIT" in self.last_agent_turn or "LAST 2 DIGIT" in self.last_agent_turn:
            self.expecting["bank_digits"] = True
        
        if "POST CODE" in self.last_agent_turn or "POSTCODE" in self.last_agent_turn:
            self.expecting["postcode"] = True
        
        if "FULL NAME" in self.last_agent_turn or "YOUR NAME" in self.last_agent_turn:
            self.expecting["full_name"] = True
        
        if "ADDRESS" in self.last_agent_turn:
            self.expecting["address"] = True
        
        if "EMAIL" in self.last_agent_turn:
            self.expecting["email"] = True
    
    def is_expecting(self, entity_type: str) -> bool:
        """Check if we're expecting a specific type of answer."""
        return self.expecting.get(entity_type, False)


class ContextAwareBankDigitsRecognizer(EntityRecognizer):
    """
    Recognizes bank digits only when agent asked for them.
    Uses EntityRecognizer base class for full custom logic.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker):
        self.context_tracker = context_tracker
        super().__init__(
            supported_entities=["BANK_ACCOUNT_LAST_DIGITS"],
            supported_language="en",
            name="ContextAwareBankDigitsRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect bank digits only if we're expecting them."""
        results = []
        
        # Only detect if agent just asked for bank digits
        if not self.context_tracker.is_expecting("bank_digits"):
            return results
        
        # Pattern 1: "DOUBLE" + digit (from converted "DOUBLE ZERO" -> "DOUBLE 0")
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
        
        # Pattern 2: Any other digits (1 or 2 digits) not already covered by DOUBLE pattern
        digit_pattern = r'\b\d{1,2}\b'
        for match in re.finditer(digit_pattern, text):
            # Check if this digit is already part of a DOUBLE match
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


class ContextAwareNameRecognizer(EntityRecognizer):
    """
    Recognizes names with conversation context awareness.
    Uses EntityRecognizer base class for full custom logic.
    """
    
    def __init__(self, context_tracker: ConversationContextTracker):
        self.context_tracker = context_tracker
        super().__init__(
            supported_entities=["PERSON"],
            supported_language="en",
            name="ContextAwareNameRecognizer"
        )
    
    def analyze(self, text, entities, nlp_artifacts):
        """Detect names with context awareness."""
        results = []
        text_upper = text.upper()
        
        # If agent just asked for full name, redact entire customer response
        # (safer than trying to parse which words are names)
        if self.context_tracker.is_expecting("full_name"):
            # Exclude common filler responses
            exclude = ["YES SIR", "NO SIR", "YEAH", "OKAY", "OK", "YES", "NO"]
            if text_upper not in exclude and len(text.split()) <= 5:
                # This is likely a name response
                results.append(RecognizerResult(
                    entity_type="PERSON",
                    start=0,
                    end=len(text),
                    score=0.95,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        pattern_name="full_name_response",
                        pattern="context_based",
                        original_score=0.95
                    )
                ))
                return results
        
        # Pattern 1: Spelled-out names
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
        
        # Pattern 2: Names after "NAME IS"
        name_intro_patterns = [
            r'NAME\s+IS\s+((?:MISSUS|MISTER|MR|MRS|MS|MISS)\s+[A-Z]{3,})',
            r'NAME\s+IS\s+([A-Z]{3,})',
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
