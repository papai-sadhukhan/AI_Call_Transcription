import re
from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult
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
			context=["name", "called", "my name is", "surname", "first name", "last name", "missus", "mr", "mrs", "ms"]
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
		results = []
		# Try to join spelled-out names
		normalized = self._join_spelled_letters(text)
		# Use a simple pattern for names (capitalized words, possibly preceded by titles)
		name_pattern = re.compile(r"(?:MISSUS|MR|MRS|MS)?\s*[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z]+)+", re.IGNORECASE)
		for match in name_pattern.finditer(normalized):
			# Contextual check
			context_window = normalized[max(0, match.start()-40):match.end()+40].lower()
			if any(c in context_window for c in self.context):
				results.append(RecognizerResult(
					entity_type="PERSON",
					start=match.start(),
					end=match.end(),
					score=0.9
				))
		return results
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
			context=["postcode", "address", "code", "location"]
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
				score=0.9
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
						score=0.95
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
from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult
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
			context=["verification", "otp", "code", "security", "pin", "auth", "login"]
		)

	def analyze(self, text, entities, nlp_artifacts):
		results = super().analyze(text, entities, nlp_artifacts)
		filtered = []

		for r in results:
			context_window = text[max(0, r.start - 40):r.end + 40].lower()
			if any(w in context_window for w in ["verification", "otp", "code", "security", "pin", "auth", "login"]):
				filtered.append(r)
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
