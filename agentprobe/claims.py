"""Says vs. does: compare what an agent TELLS the user with what it actually DID.

An agent's reply is a set of claims ("your refund has been issued") and its trajectory is the
evidence. Two checks:

  * claims_backed_by_actions: every action the reply claims was done must have a successful call.
  * actions_disclosed_in_reply: every action that was done must be mentioned in the reply.

This is pattern matching, not language understanding. It is deliberately conservative: a sentence
only counts as a claim if it matches your pattern AND is not a question, an offer, a future promise
or a negation ("I couldn't issue a refund"). Tune the patterns to your agent's wording.
"""
import re

_NEGATION = re.compile(
    r"\bnot\b|\bno\b|\bnever\b|\bunable\b|\bcannot\b|\bfailed\b|\bwithout\b|n['’]t\b", re.I
)
_NOT_A_CLAIM = re.compile(
    r"\?|\bwould you like\b|\bdo you want\b|\bcan i\b|\bcould i\b|\bshall i\b|\bshould i\b|\blet me\b|"
    r"\bi can\b|\bi could\b|\bi will\b|\bi['’]ll\b|\bi['’]m going to\b|\bif you\b|\bonce\b|"
    r"\bwill be\b|\bwill (?:receive|get|review|contact|follow)\b|\bplease\b|\bneed to\b|\bmay\b|\bmight\b",
    re.I,
)


def _patterns(spec):
    return [re.compile(p, re.I) if isinstance(p, str) else p for p in ([spec] if isinstance(spec, (str, re.Pattern)) else spec)]


def sentences(reply):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", reply or "") if s.strip()]


def is_claim(sentence, patterns):
    """A sentence that asserts, in the past or present, that something was done."""
    if _NEGATION.search(sentence) or _NOT_A_CLAIM.search(sentence):
        return False
    return any(p.search(sentence) for p in patterns)


def claimed_actions(reply, claims):
    """{tool: the first sentence that claims it was done} for every claimed tool."""
    found = {}
    for tool, spec in claims.items():
        patterns = _patterns(spec)
        for sentence in sentences(reply):
            if is_claim(sentence, patterns):
                found[tool] = sentence
                break
    return found


def mentions(reply, spec):
    """True if any sentence of the reply matches (negation doesn't matter: 'I did not delete it'
    still discloses that deletion was in play)."""
    patterns = _patterns(spec)
    return any(p.search(s) for s in sentences(reply) for p in patterns)
