"""Checks that each quoted sentence really appears on the page the agent cites."""
import re
import unicodedata
from difflib import SequenceMatcher

_MD = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")  # [text](url) → text
_PUNCT = str.maketrans({"“": '"', "”": '"', "„": '"', "’": "'", "‘": "'", "–": "-", "—": "-", " ": " ", "€": " € "})
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = _MD.sub(r"\1", s).translate(_PUNCT)
    s = re.sub(r"[*_#>`|]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s.strip(" .,:;\"'…")


def _words(s: str) -> list[str]:
    return [w.strip(".,:;\"'()…!?") for w in s.split() if w.strip(".,:;\"'()…!?")]


def check(quote: str, page_text: str) -> str:
    """Returns 'exact', 'near' or 'missing'.

    'near' allows small wording differences (an added or dropped word, an ellipsis), but every number
    in the quote must appear in the matched part of the page, so a changed fee or date never passes.
    """
    q, t = normalise(quote), normalise(page_text)
    if not q or not t:
        return "missing"
    if q in t:
        return "exact"
    qw, tw = _words(q), _words(t)
    if len(qw) < 4:
        return "missing"
    sm = SequenceMatcher(None, tw, qw, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks:
        return "missing"
    # Take the densest run of matching blocks that sits close together on the page.
    best = 0
    for i, start in enumerate(blocks):
        matched, j = 0, i
        while j < len(blocks) and blocks[j].a - start.a <= len(qw) * 1.5:
            matched += blocks[j].size
            j += 1
        if matched > best:
            best, span = matched, (start.a, blocks[j - 1].a + blocks[j - 1].size)
    if best < 0.85 * len(qw):
        return "missing"
    page_span = " ".join(tw[span[0]:span[1]])
    if any(n not in page_span for n in _NUM.findall(q)):
        return "missing"
    return "near"
