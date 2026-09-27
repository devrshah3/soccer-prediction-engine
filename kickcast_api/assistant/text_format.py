"""Strips common Markdown syntax from LLM output before it reaches the chat widget.

The frontend chat bubble renders plain text (no Markdown renderer, and adding one is
more than this needs) - without this, Gemini's "**bold**"/"`code`"/"# heading" style
formatting showed up as literal asterisks/backticks/hashes in the UI. Applied to every
assistant reply regardless of path, so DB-only template text (already plain) just passes
through unchanged.
"""

from __future__ import annotations

import re

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_BOLD_ALT = re.compile(r"__(.+?)__")
_ITALIC = re.compile(r"\*(.+?)\*")
_ITALIC_ALT = re.compile(r"(?<!\w)_(.+?)_(?!\w)")
_CODE = re.compile(r"`([^`]+)`")
_HEADER = re.compile(r"^#{1,6}\s+", re.MULTILINE)


def strip_markdown(text: str) -> str:
    text = _LINK.sub(r"\1 (\2)", text)
    text = _BOLD.sub(r"\1", text)
    text = _BOLD_ALT.sub(r"\1", text)
    text = _ITALIC.sub(r"\1", text)
    text = _ITALIC_ALT.sub(r"\1", text)
    text = _CODE.sub(r"\1", text)
    text = _HEADER.sub("", text)
    return text.strip()
