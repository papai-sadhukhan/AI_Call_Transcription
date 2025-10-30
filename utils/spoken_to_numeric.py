"""
Spoken to numeric conversion utility functions.
"""
import re
from text2digits import text2digits

def spoken_to_numeric(text: str) -> str:
    """
    Convert spoken cardinal numbers to digits, but avoid converting ordinal words
    and spoken numbers when used with units like 'pounds', 'minutes', etc.
    Also merge single-letter sequences like 'C F' -> 'CF'.
    """
    ordinals = [
        "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
        "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
        "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth",
        "nineteenth", "twentieth"
    ]
    preserve_units = ["pounds", "minutes", "days", "hours", "weeks", "months"]
    for word in ordinals:
        pattern = rf"\\b{word}\\b"
        token = f"__{word.upper()}__"
        text = re.sub(pattern, token, text, flags=re.IGNORECASE)
    for unit in preserve_units:
        pattern = rf"\\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\\s+{unit}\\b"
        text = re.sub(
            pattern,
            lambda m: f"__{m.group(0).upper().replace(' ', '_')}__",
            text,
            flags=re.IGNORECASE
        )
    t2d = text2digits.Text2Digits()
    converted = t2d.convert(text)
    for word in ordinals:
        token = f"__{word.upper()}__"
        converted = re.sub(token, word, converted, flags=re.IGNORECASE)
    for unit in preserve_units:
        for num in [
            "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
            "eighteen", "nineteen", "twenty"
        ]:
            phrase = f"{num} {unit}"
            token = f"__{phrase.upper().replace(' ', '_')}__"
            converted = re.sub(token, phrase, converted, flags=re.IGNORECASE)
    converted = re.sub(r'\\b(?:[A-Z]\\s+){1,}[A-Z]\\b', lambda m: m.group(0).replace(" ", ""), converted)
    return converted
