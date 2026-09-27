"""Lightweight regex routing for natural-language-ish queries."""

from __future__ import annotations

import re

_COMPARE_RE = re.compile(
    r"compare\s+(?:iterations?\s+)?([\d,\sand]+)",
    re.I,
)
_ITER_RE = re.compile(
    r"(?:iteration|iter|set)\s*[#:]?\s*(\d+)",
    re.I,
)
_BEST_RE = re.compile(r"\bbest\b", re.I)


def parse_query(query: str) -> tuple[str, list[int] | None]:
    """
    Returns (action, iterations).
    action: best | set | compare
    """
    text = (query or "").strip()
    if not text:
        raise ValueError("Empty query")

    m = _COMPARE_RE.search(text)
    if m:
        raw = m.group(1)
        ids = [int(x) for x in re.findall(r"\d+", raw)]
        if len(ids) < 2:
            raise ValueError("Compare query needs at least two iteration ids")
        return "compare", ids

    if _BEST_RE.search(text):
        return "best", None

    m = _ITER_RE.search(text)
    if m:
        return "set", [int(m.group(1))]

    raise ValueError(f"Could not interpret query: {query!r}")
