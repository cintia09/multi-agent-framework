"""token_estimate — deterministic token-count heuristic (M9.6 / M10.4).

Spec references this module as the single token counter for chain
summarization budget enforcement. A real tokenizer (tiktoken / claude
SDK) would replace this in the future; for now we use a deterministic
character-based heuristic that is adequate for the budget guard:

    estimate(text) = max(1, ceil(len(text) / 4))

Rationale: GPT-style BPE tokenizers compress English text at roughly
4 chars/token; CJK is closer to 1.5 chars/token but we conservatively
under-count there because the M10 chain summary budget (8192) already
includes generous overhead and pass-2 compression triggers far below
the real ceiling. The estimator is intentionally cheap, dependency-
free and side-effect-free so tests can call it deterministically.
"""

from __future__ import annotations


def estimate(text: str) -> int:
    """Return an integer token estimate for ``text`` (≥ 1)."""
    if not text:
        return 1
    return max(1, (len(text) + 3) // 4)
