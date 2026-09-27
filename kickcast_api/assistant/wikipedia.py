"""Wikipedia (MediaWiki Action API), free/keyless: the assistant's real "outside our
DB" source for match write-ups, history, and anything else our own tables don't cover -
used because Gemini's Google Search grounding is genuinely unavailable on this project's
free-tier key (confirmed real 429, see gemini_client.py's module docstring), not by
choice. Content is CC BY-SA - credited in README.md's Data credit section and cited in
every answer sourced from here.

VERIFIED against real calls (2026-09-23), User-Agent required by Wikimedia's own policy
(https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy: "<client>/<version>
(<contact>)", or requests risk being blocked without notice) - every request here sends
one identifying this project by name and contact email, per the project's own instruction.

Real bug found while building this: MediaWiki's `prop=extracts` boolean params are
presence-triggered, not value-triggered - passing `exintro=0` to ask for the FULL
article still activates intro-only mode (any value, "0" included, counts as "present").
The only way to get the full plain-text extract is to omit `exintro` entirely. Verified:
with it omitted, a real call for "2016 UEFA Champions League final" returned an 11,248
char extract containing "Sergio Ramos touched the ball past Oblak to score", "Substitute
Yannick Carrasco... equalise... in the 79th minute", and "allowing Cristiano Ronaldo to
seal Real Madrid's 11th Champions League title" - with `exintro` present (even as "0"),
the same call truncated to 958 chars and contained none of that.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from ..models import WikipediaCache

API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "KickCast/0.1 (devrshah3@gmail.com)"
MAX_EXTRACT_CHARS = 12000  # generous for a full article; keeps prompts/cache rows bounded

# MediaWiki's search is a bag-of-words relevance ranker, and interrogative/auxiliary words
# dilute it enough to rank the WRONG article top for a real question we tested this
# against: "How did Real Madrid win the 2016 Champions League final?" ranked the 2017
# final first (raw question as the query); stripping these words correctly ranks the 2016
# final first. Verified against the live API, not just reasoned about.
_STOPWORDS = frozenset({
    "how", "did", "does", "do", "what", "who", "when", "where", "why", "which",
    "is", "are", "was", "were", "will", "would", "should", "could", "can",
})


def _search_query(question: str) -> str:
    words = re.findall(r"[\w'-]+", question)
    kept = [w for w in words if w.lower() not in _STOPWORDS]
    return " ".join(kept) if kept else question


def _key(query: str) -> str:
    normalized = " ".join(query.strip().lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def _get(params: dict) -> dict | None:
    try:
        resp = requests.get(
            API_URL, params={**params, "format": "json"}, headers={"User-Agent": USER_AGENT}, timeout=10
        )
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError):
        return None


def lookup(session: Session, query: str) -> dict | None:
    """Search Wikipedia for `query`, return the top match's full plain-text extract.
    Returns None on a genuine lookup failure (network/API error - caller should treat
    this as "try again later"), or {"found": False, ...} when Wikipedia has no article
    for this (a real, cacheable answer, not an error). Cached either way by the
    normalized query so a repeated question never re-hits the API."""
    key = _key(query)
    cached = session.get(WikipediaCache, key)
    if cached is not None:
        if not cached.title:
            return {"found": False, "query": query}
        return {
            "found": True, "title": cached.title, "url": cached.url,
            "extract": cached.extract, "source": "Wikipedia (CC BY-SA)",
        }

    search = _get({"action": "query", "list": "search", "srsearch": _search_query(query), "srlimit": 1})
    if search is None:
        return None
    hits = search.get("query", {}).get("search", [])
    if not hits:
        session.add(
            WikipediaCache(
                query_hash=key, query=query, title=None, url=None, extract="",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        session.commit()
        return {"found": False, "query": query}

    title = hits[0]["title"]
    # explaintext=1 with exintro OMITTED (not "0" - see module docstring) -> full plain text.
    extracted = _get({"action": "query", "prop": "extracts", "explaintext": 1, "titles": title})
    if extracted is None:
        return None
    pages: dict = extracted.get("query", {}).get("pages", {})
    page: dict = next(iter(pages.values()), {})
    extract = (page.get("extract") or "")[:MAX_EXTRACT_CHARS]
    url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")

    session.add(
        WikipediaCache(
            query_hash=key, query=query, title=title, url=url, extract=extract,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    session.commit()
    return {"found": True, "title": title, "url": url, "extract": extract, "source": "Wikipedia (CC BY-SA)"}
