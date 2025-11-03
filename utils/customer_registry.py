import re
from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult, AnalysisExplanation
# Custom recognizer for spelled-out/phonetic names
class SpelledOutNameRecognizer(PatternRecognizer):
	"""
	Recognizes names spelled out letter-by-letter (e.g., 'J U N E P A Y N E').
	"""
	def __init__(self):
		super().__init__(
			supported_entity="PERSON",
			supported_language="en",
			name="SpelledOutNameRecognizer",
			context=["name", "called", "my name is", "surname", "first name", "last name", "missus", "mr", "mrs", "ms"],
			deny_list=["__PLACEHOLDER__"]  # Placeholder - actual detection in analyze()
		)

	def _join_spelled_letters(self, text: str) -> str:
		# Joins single-letter tokens into possible names
		tokens = text.split()
		joined = []
		buffer = []
		for t in tokens:
			if len(t) == 1 and t.isalpha():
				buffer.append(t)
			else:
				if buffer:
					joined.append("".join(buffer))
					buffer = []
				joined.append(t)
		if buffer:
			joined.append("".join(buffer))
		return " ".join(joined)

	def analyze(self, text, entities, nlp_artifacts):
		# This recognizer is replaced by ContextBasedNameRecognizer which is more accurate
		# Returning empty results to avoid false positives
		# The ContextBasedNameRecognizer handles spelled-out names better
		return []
import re
from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult
# UK postcode regex (standard format)
NATO_MAP = {
	"ALPHA": "A", "BRAVO": "B", "CHARLIE": "C", "DELTA": "D", "ECHO": "E",
	"FOXTROT": "F", "GOLF": "G", "HOTEL": "H", "INDIA": "I", "JULIETT": "J",
	"KILO": "K", "LIMA": "L", "MIKE": "M", "NOVEMBER": "N", "OSCAR": "O",
	"PAPA": "P", "QUEBEC": "Q", "ROMEO": "R", "SIERRA": "S", "TANGO": "T",
	"UNIFORM": "U", "VICTOR": "V", "WHISKEY": "W", "XRAY": "X", "YANKEE": "Y", "ZULU": "Z"
}

UK_POSTCODE_REGEX = re.compile(
	r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b",
	re.IGNORECASE
)

class SpokenPostcodeRecognizer(PatternRecognizer):
	"""
	Recognizer for UK postcodes, even when spoken phonetically (e.g. "BRAVO 775 ALPHA SIERRA").
	"""
	def __init__(self):
		super().__init__(
			supported_entity="UK_POSTCODE",
			supported_language="en",
			name="SpokenPostcodeRecognizer",
			context=["postcode", "address", "code", "location"],
			deny_list=["__PLACEHOLDER__"]  # Placeholder - actual detection in analyze()
		)

	def _decode_phonetic(self, text: str) -> str:
		tokens = re.findall(r"[A-Z]+|\d+", text.upper())
		decoded = []
		digit_words = ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"]
		for t in tokens:
			if t in NATO_MAP:
				decoded.append(NATO_MAP[t])
			elif t.isdigit():
				decoded.append(t)
			elif t in digit_words:
				decoded.append(str(digit_words.index(t)))
		return "".join(decoded)

	def analyze(self, text, entities, nlp_artifacts):
		results = []
		# Check raw text first
		for match in UK_POSTCODE_REGEX.finditer(text):
			results.append(RecognizerResult(
				entity_type="UK_POSTCODE",
				start=match.start(),
				end=match.end(),
				score=0.9,
				analysis_explanation=AnalysisExplanation(
					recognizer=self.__class__.__name__,
					pattern_name="uk_postcode",
					pattern=str(UK_POSTCODE_REGEX.pattern),
					original_score=0.9
				)
			))
		# Decode phonetic parts and re-test
		words = text.split()
		for i in range(len(words)):
			segment = " ".join(words[i:i + 8])
			decoded = self._decode_phonetic(segment)
			if decoded and UK_POSTCODE_REGEX.search(decoded):
				context_window = text[max(0, text.lower().find(segment.lower()) - 50):].lower()
				if any(c in context_window for c in ["postcode", "address", "code", "location"]):
					results.append(RecognizerResult(
						entity_type="UK_POSTCODE",
						start=text.lower().find(segment.lower()),
						end=text.lower().find(segment.lower()) + len(segment),
						score=0.95,
						analysis_explanation=AnalysisExplanation(
							recognizer=self.__class__.__name__,
							pattern_name="phonetic_postcode",
							pattern="phonetic_decoded",
							original_score=0.95
						)
					))
		return results

import re
from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult


# Improved spoken digit normalization for address detection
address_pattern = Pattern(
	name="address_pattern",
	# Match number, street type, and trailing letter/number combos (e.g. '110 AVENUE E X 47 J G')
	regex=r"\b\d{1,5}\s+(?:[A-Za-z0-9]+\s+)?(?:street|road|lane|avenue|drive|close|way|place|square|court|crescent|terrace|boulevard|highway|hill|gardens|walk|view|grove|park)(?:\s+[A-Z0-9]+)*\b",
	score=0.4,
)

SPOKEN_MAP = {
	"O": "0", "OH": "0", "ZERO": "0", "ONE": "1", "TWO": "2", "TO": "2",
	"THREE": "3", "FOUR": "4", "FOR": "4", "FIVE": "5", "SIX": "6",
	"SEVEN": "7", "EIGHT": "8", "NINE": "9"
}

def normalize_spoken(text: str) -> str:
	words = text.upper().split()
	return " ".join(SPOKEN_MAP.get(w, w) for w in words)

class SpokenAddressRecognizer(PatternRecognizer):
	def __init__(self):
		super().__init__(
			supported_entity="ADDRESS",
			supported_language="en",
			name="SpokenAddressRecognizer",
			patterns=[address_pattern],
			context=["address", "flat", "house", "road", "street", "avenue", "residence", "home"]
		)

	def analyze(self, text, entities, nlp_artifacts):
		# Normalize spoken digits first
		normalized_text = normalize_spoken(text)
		results = super().analyze(normalized_text, entities, nlp_artifacts)
		filtered = []

		for r in results:
			span = text[r.start:r.end]
			context_window = text[max(0, r.start - 100):r.end + 100].lower()

			# Context clues
			if any(word in context_window for word in self.context):
				r.score = max(r.score, 0.85)
				filtered.append(r)
				continue

			# NLP entity fallback
			entities_list = getattr(nlp_artifacts, "entities", None)
			if entities_list:
				for ent in entities_list:
					if ent.label_.lower() in ["gpe", "loc", "facility", "address"]:
						if abs(ent.start_char - r.start) < 100:
							r.score = max(r.score, 0.8)
							filtered.append(r)
							break
"""
Customer registry related functions and classes.
Custom recognizers for address, verification code, and bank account last digits.
"""
from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult, EntityRecognizer
import re

# -----------------------------------------------------------------------------
# 🏠 1. Address Recognizer (context + NLP-based confirmation)
# -----------------------------------------------------------------------------
address_pattern = Pattern(
	name="address_pattern",
	regex=r"\b\d{1,5}\s+(?:[A-Za-z0-9]+\s+)?(?:street|road|lane|avenue|drive|close|way|place|square|court|crescent|terrace|boulevard|highway|hill|gardens|walk|view|grove|park)\b",
	score=0.4  # lower base, boosted by NLP/context
)

class SpokenAddressRecognizer(PatternRecognizer):
	def __init__(self):
		super().__init__(
			supported_entity="ADDRESS",
			supported_language="en",
			name="SpokenAddressRecognizer",
			patterns=[address_pattern],
			context=["address", "flat", "house", "road", "street", "avenue", "residence", "living", "home"]
		)

	def analyze(self, text, entities, nlp_artifacts):
		results = super().analyze(text, entities, nlp_artifacts)
		filtered = []
		for r in results:
			span = text[r.start:r.end]
			context_window = text[max(0, r.start - 40):r.end + 40].lower()

			# Contextual NLP check: look for "address-like" nouns nearby
			if any(word in context_window for word in ["street", "road", "avenue", "flat", "house", "address"]):
				filtered.append(r)
			else:
				# NLP fallback: look for location entities in same sentence
				if nlp_artifacts:
					for ent in nlp_artifacts.entities:
						if ent.label_.lower() in ["gpe", "loc", "facility", "address"]:
							if abs(ent.start_char - r.start) < 50:
								filtered.append(r)
								break
		return filtered

# -----------------------------------------------------------------------------
# 🔢 2. Verification Code Recognizer (context + structure)
# -----------------------------------------------------------------------------
verification_code_pattern = Pattern(
	name="verification_code_pattern",
	regex=r"\b\d{4,6}\b",
	score=0.3  # low base, context needed to confirm
)

class VerificationCodeRecognizer(PatternRecognizer):
	def __init__(self):
		super().__init__(
			supported_entity="VERIFICATION_CODE",
			supported_language="en",
			name="VerificationCodeRecognizer",
			patterns=[verification_code_pattern],
			context=["verification", "otp", "code", "security", "pin", "auth", "login", "password", "written", "capital"]
		)

	def analyze(self, text, entities, nlp_artifacts):
		results = super().analyze(text, entities, nlp_artifacts)
		filtered = []

		for r in results:
			context_window = text[max(0, r.start - 200):r.end + 50].lower()
			password_context_keywords = [
				"verification", "otp", "code", "security", "pin", "auth", "login",
				"password", "pass word", "passcode", "verbal password",
				"written down", "write down", "noted down", "got written",
				"capital", "letter"
			]
			if any(w in context_window for w in password_context_keywords):
				# Boost score for password context
				r.score = max(r.score, 0.85)
				filtered.append(r)
		
		# Additional pattern: alphanumeric verification codes/passwords
		# Matches patterns like "X J L 215 M E", "CAPITAL X J L 215", etc.
		alphanumeric_patterns = [
			# Pattern 1: CAPITAL followed by spaced letters and numbers
			r'\b(?:CAPITAL\s+)?(?:[A-Z]\s+){2,}[A-Z0-9](?:\s+[A-Z0-9]){2,}\b',
			# Pattern 2: Mixed alphanumeric with spaces (at least 5 chars)
			r'\b[A-Z0-9](?:\s+[A-Z0-9]){4,}\b',
			# Pattern 3: Alphanumeric codes (letters and digits mixed, no spaces)
			r'\b[A-Z]{1,3}[0-9]{2,4}[A-Z]{1,3}\b',
		]
		
		for pattern in alphanumeric_patterns:
			for match in re.finditer(pattern, text):
				# Check for password/code context
				context_start = max(0, match.start() - 200)
				context_window = text[context_start:match.end() + 50].lower()
				
				password_context_keywords = [
					"password", "pass word", "passcode", "verbal password",
					"verification", "code", "security", "written down", "write down",
					"got written", "noted down", "capital", "spell"
				]
				
				if any(keyword in context_window for keyword in password_context_keywords):
					# Check if already covered by existing results
					overlap = False
					for existing in filtered:
						if not (match.end() <= existing.start or match.start() >= existing.end):
							overlap = True
							break
					
					if not overlap:
						filtered.append(RecognizerResult(
							entity_type="VERIFICATION_CODE",
							start=match.start(),
							end=match.end(),
							score=0.95,
							analysis_explanation=AnalysisExplanation(
								recognizer=self.__class__.__name__,
								pattern_name="alphanumeric_code",
								pattern=pattern,
								original_score=0.95
							)
						))
		
		return filtered

# -----------------------------------------------------------------------------
# 🏦 3. Bank Account Last Digits Recognizer (context only)
# -----------------------------------------------------------------------------
bank_digits_pattern = Pattern(
	name="bank_last_digits_pattern",
	regex=r"\b\d{2}\b",
	score=0.1  # very low, must be boosted by context
)

class BankLastDigitsRecognizer(PatternRecognizer):
	def __init__(self):
		super().__init__(
			supported_entity="BANK_ACCOUNT_LAST_DIGITS",
			supported_language="en",
			name="BankLastDigitsRecognizer",
			patterns=[bank_digits_pattern],
			context=["bank", "account", "digits", "last", "ending", "sort code", "balance"]
		)

	def analyze(self, text, entities, nlp_artifacts):
		results = super().analyze(text, entities, nlp_artifacts)
		filtered = []

		for r in results:
			context_window = text[max(0, r.start - 50):r.end + 50].lower()
			if any(w in context_window for w in ["bank", "account", "digits", "ending", "sort code", "balance"]):
				# Avoid date-like matches (e.g., 20 October)
				if not re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|th|st|nd|rd)\b", context_window):
					filtered.append(r)
		return filtered


# -----------------------------------------------------------------------------
# 🚫 4. False Positive Filter (removes common misclassifications)
# -----------------------------------------------------------------------------
class FalsePositiveFilterRecognizer:
	"""
	Utility class that filters out common false positives.
	Specifically targets pronouns and contractions misclassified as PERSON entities.
	This is NOT a Presidio recognizer - it's a filter used in post-processing.
	"""
	
	# Comprehensive list of pronouns and contractions often misclassified as names
	FALSE_POSITIVE_WORDS = {
		"YOU'RE", "I'M", "WE'RE", "THEY'RE", "HE'S", "SHE'S", "IT'S", "THAT'S",
		"YOU", "I", "WE", "THEY", "HE", "SHE", "ME", "US", "THEM", "HIM", "HER",
		"YOUR", "MY", "OUR", "THEIR", "HIS", "MINE", "YOURS", "THEIRS",
		"YOU'VE", "I'VE", "WE'VE", "THEY'VE", "WHO'S", "WHAT'S", "WHERE'S",
		"YOURSELF", "MYSELF", "OURSELVES", "THEMSELVES", "HIMSELF", "HERSELF"
	}
	
	@classmethod
	def is_false_positive(cls, text: str, entity_type: str, context: str) -> bool:
		"""
		Check if a detected entity is a false positive.
		
		Args:
			text: The matched text
			entity_type: The detected entity type
			context: Surrounding text for context validation
			
		Returns:
			True if the entity should be filtered out (is a false positive)
		"""
		text_upper = text.upper().strip()
		
		# Filter common pronouns and contractions for PERSON entities
		if entity_type == "PERSON":
			if text_upper in cls.FALSE_POSITIVE_WORDS:
				return True
			
			# Single letters are likely not names unless in specific name-spelling context
			if len(text_upper) == 1 and "SPELL" not in context.upper():
				return True
			
			# Filter the word "NAME" itself when detected alone
			if text_upper == "NAME":
				return True
			
			# Filter phrases that contain name-related keywords but aren't actual names
			# These are questions about names, not the names themselves
			name_question_phrases = [
				"KNOW YOUR", "FULL NAME", "NAME PLEASE", "YOUR NAME", "FIRST NAME",
				"LAST NAME", "SURNAME", "MAIDEN NAME", "CHRISTIAN NAME",
				"MY NAME IS", "NAME IS MISSUS", "NAME IS MR", "NAME IS MS",
				"NAME IS MISS", "NAME IS MRS", "NAME AND MY", "THAT'S MY",
				"S MY", "MY CHRISTIAN", "MY SURNAME", "MY FIRST", "MY LAST",
				"HELLO THERE", "THANK YOU FOR", "CALLING SKY", "HOW CAN I HELP"
			]
			
			# If the matched text contains these phrases, it's likely a question/greeting, not a name
			for phrase in name_question_phrases:
				if phrase in text_upper:
					return True
			
			# Filter very long matches (likely phrases, not names)
			# Real names are typically 2-4 words, not 5+
			word_count = len(text_upper.split())
			if word_count > 4:
				# Exception: spelled-out names with spaces like "A P P L E"
				# These will have many single-letter words
				single_letter_words = sum(1 for word in text_upper.split() if len(word) == 1)
				if single_letter_words < word_count * 0.6:  # Less than 60% single letters
					return True
		
		return False


# -----------------------------------------------------------------------------
# � 5. Context-Based Name Recognizer (detects spelled-out names and name responses)
# -----------------------------------------------------------------------------
class ContextBasedNameRecognizer(PatternRecognizer):
	"""
	Recognizes names based on conversational context.
	Detects:
	- Spelled-out names: "A P P L E" or "R O S E"
	- Name responses after name questions
	- Mother's maiden names
	- Christian names, surnames
	"""
	
	NAME_CONTEXT_KEYWORDS = [
		"name is", "my name", "called", "surname", "maiden name",
		"christian name", "first name", "last name", "mother's",
		"missus", "mr", "mrs", "ms", "mister"
	]
	
	def __init__(self):
		super().__init__(
			supported_entity="PERSON",
			supported_language="en",
			name="ContextBasedNameRecognizer",
			context=self.NAME_CONTEXT_KEYWORDS,
			deny_list=["__PLACEHOLDER__"]  # Placeholder - actual detection in analyze()
		)
	
	def analyze(self, text, entities, nlp_artifacts):
		"""
		Detect names based on conversational context.
		"""
		results = []
		text_upper = text.upper()
		
		# Check for name context
		context_start = max(0, len(text_upper) - 500)
		context_window = text_upper[context_start:].lower()
		
		has_name_context = any(keyword in context_window for keyword in self.NAME_CONTEXT_KEYWORDS)
		
		# Pattern 0: Special case - "HELLO [NAME]" or "HI [NAME]" at start (for greeting responses)
		# This doesn't require name context but validates the word is not common
		greeting_patterns = [
			r'^(?:HELLO|HI)\s+([A-Z]{3,})',
			r'\.\s+(?:HELLO|HI)\s+([A-Z]{3,})',
		]
		
		common_greeting_words = {'THERE', 'SIR', 'MADAM', 'HOW', 'CAN', 'MAY', 'THIS', 'THE'}
		
		for pattern in greeting_patterns:
			for match in re.finditer(pattern, text_upper):
				name_text = match.group(1)
				# Only detect if it's not a common word
				if name_text not in common_greeting_words and len(name_text) >= 3:
					name_start = match.start(1)
					name_end = match.end(1)
					results.append(RecognizerResult(
						entity_type="PERSON",
						start=name_start,
						end=name_end,
						score=0.85,
						analysis_explanation=AnalysisExplanation(
							recognizer=self.__class__.__name__,
							pattern_name="greeting_response",
							pattern=pattern,
							original_score=0.85
						)
					))
		
		if not has_name_context:
			return results
		
		# Pattern 1: Detect spelled-out names (e.g., "A P P L E" or "R O S E")
		# Must be 3+ letters, each separated by space
		spelled_pattern = r'\b([A-Z]\s+){2,}[A-Z]\b'
		for match in re.finditer(spelled_pattern, text_upper):
			# Remove spaces to check if it forms a reasonable name
			spelled_text = match.group().replace(' ', '')
			if len(spelled_text) >= 3:  # At least 3 letters
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
		
		# Pattern 2: Names after specific phrases
		# Match: "MY NAME IS [TITLE] NAME" or "NAME IS NAME" or "CALLED NAME" or "MAIDEN NAME NAME"
		name_introduction_patterns = [
			# After "NAME IS" with optional title (MISSUS, MR, MRS, MS, MISS) - capture title + name together
			r'NAME\s+IS\s+((?:MISSUS|MISTER|MR|MRS|MS|MISS)\s+[A-Z]{3,})',
			# After "NAME IS" without title - just the name
			r'NAME\s+IS\s+([A-Z]{3,})',
			# After "CALLED" with optional title
			r'CALLED\s+((?:MISSUS|MISTER|MR|MRS|MS|MISS)\s+[A-Z]{3,})',
			r'CALLED\s+([A-Z]{3,})',
			# After "MAIDEN NAME"
			r'MAIDEN\s+NAME\s+(?:IS)?\s*([A-Z]{3,})',
			# After "SURNAME IS"
			r'SURNAME\s+IS\s+((?:MISSUS|MISTER|MR|MRS|MS|MISS)\s+[A-Z]{3,})',
			r'SURNAME\s+IS\s+([A-Z]{3,})',
		]
		
		for pattern in name_introduction_patterns:
			for match in re.finditer(pattern, text_upper):
				# Extract the captured name
				name_text = match.group(1)
				
				# Check it's not a common word or title
				common_words = {'THE', 'AND', 'FOR', 'YOU', 'YES', 'NOT', 'BUT', 'ARE', 'CAN', 'WAS', 
				                'MISSUS', 'MISTER', 'MISS'}
				if name_text not in common_words and len(name_text) >= 3:
					# Find position of the captured group in the original text
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
# 🏠 6. Full Address Line Recognizer (context-based complete address redaction)
# -----------------------------------------------------------------------------
class FullAddressLineRecognizer(PatternRecognizer):
	"""
	Recognizes complete address lines when in address context.
	Redacts entire response when customer provides address.
	"""
	
	ADDRESS_REQUEST_KEYWORDS = [
		"address", "post code", "postcode", "first line", "line of the address"
	]
	
	def __init__(self):
		super().__init__(
			supported_entity="ADDRESS",
			supported_language="en",
			name="FullAddressLineRecognizer",
			context=self.ADDRESS_REQUEST_KEYWORDS,
			deny_list=["__PLACEHOLDER__"]  # Placeholder - actual detection in analyze()
		)
	
	def analyze(self, text, entities, nlp_artifacts):
		"""
		Detect complete address responses.
		Context keywords boost score, but addresses with street indicators are detected anyway.
		"""
		results = []
		text_upper = text.upper()
		
		# Check for address context keywords (optional - boosts confidence)
		context_start = max(0, len(text_upper) - 500)
		context_window = text_upper[context_start:].lower()
		
		has_address_context = any(keyword in context_window for keyword in self.ADDRESS_REQUEST_KEYWORDS)
		
		# Note: We don't return early - addresses with street words will be detected anyway
		
		# Pattern 1: Number + Street name pattern (e.g., "29 LAMPTON AVENUE S S 25 N X")
		# With optional postcode at end
		address_patterns = [
			# Full address with flexible postcode: "29 LAMPTON AVENUE S S 25 N X" or "29 WINDSOR AVENUE S S 88 N X"
			# UK postcode spaced out: letter(s) space digit(s) space letter(s)
			r'\b\d{1,4}\s+[A-Z]+(?:\s+[A-Z]+)*\s+(?:[A-Z]\s+){1,2}(?:\d+\s+)?[A-Z](?:\s+[A-Z])?\b',
			# Address without postcode: "29 LAMPTON AVENUE"
			r'\b\d{1,4}\s+[A-Z]+(?:\s+[A-Z]+){1,5}\b'
		]
		
		for pattern in address_patterns:
			for match in re.finditer(pattern, text_upper):
				# Check if it looks like a real address (has common street words or long enough)
				matched_text = match.group()
				street_indicators = ['STREET', 'ROAD', 'AVENUE', 'LANE', 'DRIVE', 'WAY', 'CLOSE', 'COURT', 'PLACE', 'SQUARE', 'GARDENS']
				
				# Exclude common false positives (phrases from questions)
				false_positive_words = ['LINE OF', 'PART OF', 'SOME OF', 'ONE OF', 'OUT OF']
				has_false_positive = any(fp in matched_text for fp in false_positive_words)
				
				has_street_word = any(word in matched_text for word in street_indicators)
				is_long_enough = len(matched_text.split()) >= 3
				
				# Only detect if it has street words OR has explicit address context
				# This prevents false positives while catching real addresses
				if not has_false_positive and (has_street_word or has_address_context):
					# Higher score if context is present
					score = 0.95 if has_address_context else 0.85
					results.append(RecognizerResult(
						entity_type="ADDRESS",
						start=match.start(),
						end=match.end(),
						score=score,
						analysis_explanation=AnalysisExplanation(
							recognizer=self.__class__.__name__,
							pattern_name="address_line",
							pattern=pattern,
							original_score=score
						)
					))
		
		return results


# -----------------------------------------------------------------------------
# �🔐 7. Enhanced Password/Code Recognizer (alphanumeric patterns with context)
# -----------------------------------------------------------------------------
class AlphanumericPasswordRecognizer(PatternRecognizer):
	"""
	Recognizer for alphanumeric passwords and verification codes.
	Detects patterns like "CAPITAL X J L 215 M E" or "A B C 1 2 3".
	Requires strong password context to avoid false positives.
	"""
	
	PASSWORD_CONTEXT_KEYWORDS = [
		"password", "pass word", "passcode", "verbal password",
		"verification", "verification code", "code", "security code",
		"written down", "write down", "got written", "noted down",
		"capital", "spell", "letter", "pin", "auth"
	]
	
	def __init__(self):
		super().__init__(
			supported_entity="PASSWORD",
			supported_language="en",
			name="AlphanumericPasswordRecognizer",
			context=self.PASSWORD_CONTEXT_KEYWORDS,
			deny_list=["__PLACEHOLDER__"]  # Placeholder - actual detection in analyze()
		)
	
	def analyze(self, text, entities, nlp_artifacts):
		"""
		Detect alphanumeric passwords using multiple pattern strategies.
		Only matches when strong password context is present.
		"""
		results = []
		text_upper = text.upper()
		
		# Check for password context in a larger window (look back 500 chars)
		context_start = max(0, len(text_upper) - 500)
		context_window = text_upper[context_start:].lower()
		
		has_password_context = any(keyword in context_window for keyword in self.PASSWORD_CONTEXT_KEYWORDS)
		
		if not has_password_context:
			return results
		
		# When password context is strong, be more aggressive in detection
		# Pattern 1: Anything after common password introduction phrases
		password_intro_patterns = [
			r'(?:PASSWORD\s+IS|COME\s+UP|CHANGED\s+IT)[^A-Z]*([A-Z0-9\s]{5,})',
			r'(?:LATE|CODE\s+IS|PIN\s+IS)[^A-Z]*([A-Z0-9\s]{3,})',
		]
		
		for pattern in password_intro_patterns:
			for match in re.finditer(pattern, text_upper):
				# Extract the password part
				password_match = re.search(r'([A-Z0-9\s]+)', match.group())
				if password_match:
					# Calculate position in original text
					pwd_start = match.start() + match.group().find(password_match.group())
					pwd_end = pwd_start + len(password_match.group().rstrip())
					
					results.append(RecognizerResult(
						entity_type="PASSWORD",
						start=pwd_start,
						end=pwd_end,
						score=0.95,
						analysis_explanation=AnalysisExplanation(
							recognizer=self.__class__.__name__,
							pattern_name="password_intro",
							pattern=pattern,
							original_score=0.95
						)
					))
		
		# Pattern 2: Spelled-out alphanumeric codes (e.g., "CAPITAL X J L 215 M E")
		alphanumeric_patterns = [
			# CAPITAL followed by spaced letters and numbers (flexible - allows multi-digit nums)
			r'\bCAPITAL\s+(?:[A-Z]|\d+)(?:\s+(?:[A-Z]|\d+)){3,}\b',
			# Mixed alphanumeric with spaces (letters and numbers, at least 4 parts)
			r'\b(?:[A-Z]|\d+)(?:\s+(?:[A-Z]|\d+)){3,}\b',
			# Alphanumeric codes (letters and digits mixed, no spaces)
			r'\b[A-Z]{1,3}[0-9]{2,4}[A-Z]{1,3}\b',
		]
		
		for pattern in alphanumeric_patterns:
			for match in re.finditer(pattern, text_upper):
				# Check if already covered by existing results
				overlap = False
				for existing in results:
					if not (match.end() <= existing.start or match.start() >= existing.end):
						overlap = True
						break
				
				if not overlap:
					results.append(RecognizerResult(
						entity_type="PASSWORD",
						start=match.start(),
						end=match.end(),
						score=0.95,
						analysis_explanation=AnalysisExplanation(
							recognizer=self.__class__.__name__,
							pattern_name="alphanumeric_password",
							pattern=pattern,
							original_score=0.95
						)
					))
		
		return results
