"""Fixture: LLM docstrings/comments that paraphrase code in synonyms.

None of these share enough words with the code for the lexical rules
(CM301/CM302) to fire — only the semantic tier (CM307) catches them.
"""


def combine_pair(first_value, second_value):
    """Adds the two inputs together and returns their total."""
    return first_value + second_value


def gather_valid(entries):
    """Iterates over the entries and appends each valid one to a fresh list."""
    kept = []
    for entry in entries:
        if entry.valid:
            kept.append(entry)
    return kept


def active_total(users):
    total = 0
    # walks each record and bumps the total
    for user in users:
        if user.active:
            total += 1
    return total
