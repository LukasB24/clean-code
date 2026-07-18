"""Clause splitting and narration-shape detection for what/why scoring.

A composite comment ("Computes matrix multiplication using block-striping to
maximize L1 cache hits.") mixes a procedural description with its rationale,
and scoring it whole would let the mean embedding dilute either part — so the
classifier judges clauses: sentence fragments, additionally cut where a
rationale connective ("because ...", "to maximize ...") starts. Splitting
keeps the connective with the tail so the classifier sees the purpose
framing; a missed split errs toward *not* flagging, the safe direction for a
linter. Inline code spans are removed first: they are identifiers, not
prose, and punctuation inside them (````__all__ = [...]````) would fake
sentence boundaries.

``narration_shaped`` is the deterministic gate in front of the classifier.
Mean-pooled embeddings are blind to word order, so it alone tells verb-led
narration ("Groups the records by key") from a noun-led value contract
("Groups of functions whose bodies collide" — the giveaway for ambiguous
openers is the ``of`` right after). Only narration-shaped clauses ever reach
the classifier.
"""

from __future__ import annotations

import re

_SENTENCE_BOUNDARY = re.compile(r"[.;:!?\n]+")
_CODE_SPAN = re.compile(r"``.*?``|`[^`]*`")

# Bare "to" is deliberately not a boundary — "converts the string to
# lowercase" is one procedural clause, not two.
_RATIONALE_CONNECTIVE = re.compile(
    r"\b(?:because|since|so\b|in order to|rather than|instead of|otherwise|unless"
    r"|which (?:avoids|prevents|ensures|guarantees|keeps|makes|saves|lets)"
    r"|to (?:avoid|prevent|ensure|guarantee|keep|preserve|protect|reduce|improve"
    r"|support|match|maintain|stay|remain|amortize|speed|save|let|make"
    r"|maximi[sz]e|minimi[sz]e|optimi[sz]e))\b",
    re.IGNORECASE,
)

# Verbs that open procedural narration; matched through the stemmer, so
# inflections ("Adds", "Iterating") need no entries of their own.
PROCEDURAL_LEAD_VERBS = frozenset(
    """
    add take get set compute calculate process handle perform execute run make
    create iterate loop walk traverse scan search find look check test verify
    determine convert cast turn parse serialize encode decode split join
    concatenate strip replace pad truncate format build construct merge update
    copy swap sort order reverse filter keep map collect flatten group zip
    unpack slice extract index access mutate modify change reset clear empty
    fill populate toggle initialize instantiate define declare import open
    read write save close load fetch retrieve obtain store assign send receive
    download upload print log display show return give yield produce output
    wrap raise throw catch call invoke delegate forward query aggregate
    combine generate sum subtract multiply divide increment decrement round
    clamp normalize apply move train evaluate predict tokenize shuffle skip
    start stop count append remove delete insert pop push use do go score
    repeat accumulate enumerate escape validate transform
    """.split()
)

# Meta-subject lead-ins narration hides behind: "This function takes ...",
# "helper that converts ...". A bare article is never stripped on its own —
# that would turn the noun contract "The score paired with ..." verb-led.
_META_LEAD_IN = re.compile(
    r"^(?:(?:this|the|a|an)\s+)?(?:function|method|helper|routine|utility|wrapper)\s+(?:that\s+|which\s+)?"
    r"|^(?:it|we)\s+",
    re.IGNORECASE,
)
_FIRST_WORDS = re.compile(r"[a-z]+")


def narration_shaped(clause: str) -> bool:
    """Whether ``clause`` opens like verb-led procedural narration."""
    from cleancode.rules.base import stem_candidates

    words = _FIRST_WORDS.findall(_META_LEAD_IN.sub("", clause.lower(), count=1))
    if not words or (len(words) > 1 and words[1] == "of"):
        return False
    return bool(stem_candidates(words[0]) & PROCEDURAL_LEAD_VERBS)


def clauses(text: str) -> list[str]:
    """Non-empty clauses of ``text``: sentences, cut again at rationale connectives."""
    pieces: list[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(_CODE_SPAN.sub(" ", text)):
        pieces.extend(_cut_at_connectives(sentence.strip()))
    return [clause for clause in pieces if clause]


def _cut_at_connectives(sentence: str) -> list[str]:
    boundaries = [match.start() for match in _RATIONALE_CONNECTIVE.finditer(sentence)]
    starts = [0] + [boundary for boundary in boundaries if boundary > 0]
    pieces = [sentence[start:end].strip() for start, end in zip(starts, starts[1:] + [len(sentence)])]
    return [piece for piece in pieces if piece]
