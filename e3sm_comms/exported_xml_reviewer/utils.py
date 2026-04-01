from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import urlsplit


def normalize_status(raw_status: Optional[str]) -> str:
    if not raw_status:
        return "unknown"

    mapping = {
        "publish": "published",
        "archive": "archived",
        "draft": "draft",
        "future": "future",
        "pending": "pending",
        "private": "private",
    }
    return mapping.get(raw_status.strip().lower(), raw_status.strip().lower())


def display_status(status: str) -> str:
    mapping = {
        "published": "Published",
        "archived": "Archived",
        "draft": "Draft",
        "future": "Future",
        "pending": "Pending",
        "private": "Private",
        "unknown": "Unknown",
    }
    return mapping.get(status, status.title())


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_legacy_content_url(url: str) -> bool:
    parts = urlsplit(url)
    slug = parts.path.strip("/").lower()
    return bool(re.fullmatch(r"\d{6,8}[_-].+", slug))


def count_sensitive_terms(text: str, terms: List[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    lowered = text.lower()

    for term in terms:
        escaped = re.escape(term)
        pattern = rf"\b{escaped}\b"
        matches = re.findall(pattern, lowered)
        if matches:
            counts[term] = len(matches)

    return counts
