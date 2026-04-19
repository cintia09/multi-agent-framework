"""Secret scanner shared by all extractors (M9.4 refactor).

Originally inlined in ``knowledge-extractor/extract.py``; lifted here so
the M9.4 skill-extractor (and future M9.5 config-extractor) reuse the
same fail-close rule set without copy-paste drift.

Public API::

    SECRET_PATTERNS                   # list[(rule_id, compiled_regex)]
    scan_secrets(text) -> (bool, rule_id|None)
    redact(text)      -> str
"""

from __future__ import annotations

import re

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("github-pat", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("rsa-private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("internal-ip-10", re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    ("internal-ip-192", re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b")),
    ("internal-ip-172", re.compile(r"\b172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b")),
    ("internal-ipv6-ula", re.compile(r"\b[fF][cdCD][0-9a-fA-F]{2}:[0-9a-fA-F:]*\b")),
    (
        "connection-string",
        re.compile(
            r"(?:postgres|postgresql|mysql|mongodb|redis)://[^\s\"']+",
            re.IGNORECASE,
        ),
    ),
]


def scan_secrets(text: str) -> tuple[bool, str | None]:
    """Return ``(hit, rule_id)`` — *hit* is True on first matching rule."""
    for rule_id, pat in SECRET_PATTERNS:
        if pat.search(text or ""):
            return True, rule_id
    return False, None


def redact(text: str) -> str:
    """Replace every match of every rule with ``***``."""
    out = text or ""
    for _rule_id, pat in SECRET_PATTERNS:
        out = pat.sub("***", out)
    return out
