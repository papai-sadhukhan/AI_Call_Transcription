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
