import spacy
import sys

# Usage: python inspect_entity.py "Your text here"
if len(sys.argv) > 1:
    text = sys.argv[1]
else:
    text = "ALRIGHT I WILL HELP YOU WITH THAT FIRST OF ALL I JUST NEED TO VERIFY THE DETAILS SO CAN YOU CONFIRM YOUR FULL NAME ON THE ACCOUNT IF YOU DON'T MIND"

nlp = spacy.load("en_core_web_lg")
doc = nlp(text)

print(f"Text: {text}\nEntities:")
for ent in doc.ents:
    print(f"{ent.text} -> {ent.label_}")