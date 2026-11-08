import re

from mcp_service.config import MAX_TEXT_LEN

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACES = re.compile(r"\s+")


def clean_text(value: str | None, limit: int = MAX_TEXT_LEN) -> str:
    """Text scraped from the chains' sites, made safe to hand to Claude: one line, no control characters, short.
    It is data (a product name, a promotion's wording), never an instruction."""
    if not value:
        return ""
    text = _SPACES.sub(" ", _CONTROL.sub("", value)).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
