#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optional fresh topic sourcing using lightweight RSS queries.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


from infrastructure.utils.text_utils import normalize_text


def fresh_topics_enabled() -> bool:
    value = os.getenv("ENABLE_FRESH_TOPICS", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _normalise_topic(text: str) -> str:
    """Normalize topic for comparison (alias for normalize_text)"""
    return normalize_text(text)


def _clean_headline(title: str) -> str:
    cleaned = re.sub(r"\s*[-|—]\s*[^-|—]+$", "", title).strip()
    return re.sub(r"\s+", " ", cleaned)


def _query_candidates(
    account_config: dict[str, Any], preferred_pillar: Optional[str] = None
) -> list[str]:
    niche = str(account_config.get("niche", "")).strip()
    pillars = account_config.get("content_pillars", {})
    pillar_names = [str(name).replace("_", " ").strip() for name in pillars.keys()]

    queries: list[str] = []
    if preferred_pillar:
        queries.append(preferred_pillar.replace("_", " ").strip())
    queries.extend(pillar_names[:2])
    if niche:
        queries.append(niche)

    if not queries:
        queries.append("technology")

    unique_queries: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = _normalise_topic(query)
        if normalized and normalized not in seen:
            unique_queries.append(query)
            seen.add(normalized)
    return unique_queries[:3]


def fetch_fresh_topic_candidates(
    account_config: dict[str, Any], preferred_pillar: Optional[str] = None, limit: int = 10
) -> list[str]:
    titles: list[str] = []

    for query in _query_candidates(account_config, preferred_pillar):
        search_query = f"{query} when:7d"
        url = f"https://news.google.com/rss/search?q={quote_plus(search_query)}&hl=en-US&gl=US&ceid=US:en"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

        try:
            with urlopen(request, timeout=8) as response:
                payload = response.read()
        except (URLError, OSError, TimeoutError):
            # Network errors, skip this feed
            continue

        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            continue

        for item in root.findall(".//item/title"):
            title = _clean_headline(item.text or "")
            if title:
                titles.append(title)
                if len(titles) >= limit:
                    return titles

    return titles


def pick_fresh_topic(
    account_config: dict[str, Any],
    recent_topics: list[str],
    preferred_pillar: Optional[str] = None,
) -> Optional[str]:
    recent = {_normalise_topic(topic) for topic in recent_topics if topic}

    for candidate in fetch_fresh_topic_candidates(
        account_config, preferred_pillar=preferred_pillar, limit=12
    ):
        normalized = _normalise_topic(candidate)
        if normalized and normalized not in recent:
            return candidate

    return None


__all__ = [
    "fetch_fresh_topic_candidates",
    "fresh_topics_enabled",
    "pick_fresh_topic",
]
