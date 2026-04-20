"""text_fingerprint — deterministic, stdlib-only fuzzy-text helpers.

Used by :mod:`memory_layer` (change E) to detect and merge near-duplicate
``by_topic`` / skill entries at *write time*, so two different tasks that
independently propose the same knowledge end up reinforcing a single
canonical file instead of fragmenting the store.

Design:
    * No external embedding dependency — uses ``difflib`` and shingled
      Jaccard on a normalized, lowercase, punctuation-stripped form.
    * Deterministic, target-budget < 50 ms per comparison on the ~300
      char fingerprints we materialize from file bodies.
    * All thresholds are module constants so callers / tests can patch
      them without branching the decision logic.
"""
from __future__ import annotations

import difflib
import re

# ---------------------------------------------------------------- constants

#: Body fingerprint window — we only compare the leading window of each
#: normalized body so very long docs still get a fast, deterministic
#: comparison. Aligned with the "first ~300 chars" rule in the change-E
#: spec.
FINGERPRINT_CHARS = 300

#: Shingle size for the Jaccard / substring-overlap estimator. 4-word
#: shingles are long enough to avoid collisions on common function
#: words while still catching paraphrases.
SHINGLE_SIZE = 4

#: Minimum SequenceMatcher ratio on the normalized fingerprint to
#: trigger a fuzzy merge.
BODY_FINGERPRINT_THRESHOLD = 0.85

#: Minimum Jaccard (over 4-word shingles) to trigger a fuzzy merge.
SUBSTRING_OVERLAP_THRESHOLD = 0.70

#: Minimum fraction of new-body shingles that are absent from the
#: existing body for us to append a dated "Update — <task>" section
#: during merge. Below this, we record the source link only.
MATERIAL_NEW_RATIO = 0.20

#: Minimum SequenceMatcher body ratio required *in addition to* a
#: normalized-title equality before :func:`is_fuzzy_match` returns True
#: on the title path. Without this guard, generic titles ("Key
#: Findings", "Summary", "Notes", "Gotchas") from unrelated tasks would
#: collapse into a single incoherent file.
TITLE_MATCH_MIN_BODY_RATIO = 0.30

_WORD_RE = re.compile(r"[a-z0-9]+")


# ---------------------------------------------------------------- normalization


def normalize_title(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return " ".join(_WORD_RE.findall((text or "").lower()))


def normalize_fingerprint(text: str, max_chars: int = FINGERPRINT_CHARS) -> str:
    """Normalize *text* for similarity comparison.

    Lowercase, drop everything except ``[a-z0-9]`` tokens, join with a
    single space, truncate to *max_chars*. Stable / deterministic.
    """
    tokens = _WORD_RE.findall((text or "").lower())
    joined = " ".join(tokens)
    return joined[:max_chars]


# ---------------------------------------------------------------- similarity


def similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio over two pre-normalized fingerprints."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _shingles(text: str, size: int = SHINGLE_SIZE) -> set[str]:
    words = _WORD_RE.findall((text or "").lower())
    if not words:
        return set()
    if len(words) < size:
        return set(words)
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def substring_overlap(a: str, b: str) -> float:
    """Jaccard similarity over 4-word shingles.

    Used as a second-opinion signal: two docs can have a moderate
    SequenceMatcher ratio but very high shingle overlap when one is a
    near-subset of the other (classic "mostly the same, with a bit of
    extra" case).
    """
    sa = _shingles(a)
    sb = _shingles(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    if union == 0:
        return 0.0
    return inter / union


def new_content_ratio(new_body: str, existing_body: str) -> float:
    """Fraction of *new_body* shingles absent from *existing_body*.

    1.0 ⇒ completely new evidence; 0.0 ⇒ already fully contained. Used
    to decide whether a fuzzy-merge should append an "Update" section.
    """
    sa = _shingles(new_body)
    if not sa:
        return 0.0
    sb = _shingles(existing_body)
    if not sb:
        return 1.0
    return len(sa - sb) / len(sa)


# ---------------------------------------------------------------- decision


def is_fuzzy_match(
    new_title: str,
    new_body: str,
    existing_title: str,
    existing_body: str,
    *,
    body_threshold: float = BODY_FINGERPRINT_THRESHOLD,
    overlap_threshold: float = SUBSTRING_OVERLAP_THRESHOLD,
) -> tuple[bool, str, float]:
    """Return ``(matched, reason, score)``.

    ``reason`` ∈ {``title_normalized_match``, ``body_fingerprint``,
    ``substring_overlap``, ``no_match``}. ``score`` is the dominant
    numeric signal (title path reports the body ratio that passed the
    sanity gate).

    Title-equality is gated by a minimum body similarity
    (:data:`TITLE_MATCH_MIN_BODY_RATIO`) so that generic titles like
    "Key Findings", "Summary", "Notes" do not merge unrelated entries.
    """
    nt_new = normalize_title(new_title)
    nt_ex = normalize_title(existing_title)

    fp_new = normalize_fingerprint(new_body)
    fp_ex = normalize_fingerprint(existing_body)
    body_ratio = similarity(fp_new, fp_ex)

    # Option A (post-D+E review): title-eq alone is not enough — require
    # a minimum body similarity, otherwise two unrelated "Key Findings"
    # files get welded together.
    if nt_new and nt_new == nt_ex and body_ratio >= TITLE_MATCH_MIN_BODY_RATIO:
        return True, "title_normalized_match", body_ratio

    if body_ratio >= body_threshold:
        return True, "body_fingerprint", body_ratio

    overlap = substring_overlap(new_body, existing_body)
    if overlap >= overlap_threshold:
        return True, "substring_overlap", overlap

    return False, "no_match", max(body_ratio, overlap)
