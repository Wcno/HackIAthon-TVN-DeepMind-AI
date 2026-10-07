"""Neutralizing text from sources so it cannot open or close a tag of the prompt (T07).

Angle brackets are replaced by look-alike characters. A passage the model copies back with them is mapped to the
original brackets before citations are checked, so a citation stays literal against the stored evidence.
"""

NEUTRAL_BRACKETS = str.maketrans({"<": "‹", ">": "›"})
RESTORED_BRACKETS = str.maketrans({"‹": "<", "›": ">"})


def neutralize(text: str) -> str:
    return text.translate(NEUTRAL_BRACKETS)


def restore_brackets(text: str) -> str:
    return text.translate(RESTORED_BRACKETS)


def was_altered(text: str) -> bool:
    return neutralize(text) != text
