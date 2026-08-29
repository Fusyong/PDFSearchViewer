from __future__ import annotations

import re

from .models import NormalizeOptions

# Fullwidth digits ０-９ -> 0-9
_FULLWIDTH_DIGIT_TRANS = str.maketrans(
    {ord("０") + i: ord("0") + i for i in range(10)}
)

_DASH_RE = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\-]+")


def is_whitespace_char(ch: str) -> bool:
    if not ch:
        return True
    if ch in "\u3000\xa0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f":
        return True
    return ch.isspace()


def apply_char_rules(ch: str, options: NormalizeOptions) -> str | None:
    """
    Transform a single character under normalize options.
    Returns None if the character should be dropped (e.g. whitespace when stripping).
    """
    if options.strip_whitespace and is_whitespace_char(ch):
        return None
    out = ch
    if options.unify_digits:
        out = out.translate(_FULLWIDTH_DIGIT_TRANS)
    if options.unify_dashes and _DASH_RE.fullmatch(out):
        out = "-"
    return out


def build_normalized_stream(
    raw_text: str,
    stream_map: list[int],
    options: NormalizeOptions,
) -> tuple[str, list[int]]:
    """
    Build a searchable string from raw_text under options.
    Returns (normalized_text, map_from_norm_index_to_stream_index).
    stream_map entries of -1 (inserted newlines) are treated as whitespace.
    """
    if not options.any_enabled():
        return raw_text, list(range(len(raw_text)))

    norm_chars: list[str] = []
    norm_to_stream: list[int] = []

    for i, ch in enumerate(raw_text):
        # Inserted line breaks count as whitespace for strip purposes
        if stream_map[i] < 0:
            if options.strip_whitespace:
                continue
            norm_chars.append(ch)
            norm_to_stream.append(i)
            continue

        transformed = apply_char_rules(ch, options)
        if transformed is None:
            continue
        # unify_dashes may collapse multi-dash in future; per-char for now
        if options.unify_dashes and len(transformed) == 1 and transformed == "-":
            if norm_chars and norm_chars[-1] == "-":
                continue
        norm_chars.append(transformed)
        norm_to_stream.append(i)

    return "".join(norm_chars), norm_to_stream


def normalize_display_text(text: str, options: NormalizeOptions) -> str:
    """Normalize a plain string for display / grouping (no stream map)."""
    if not options.any_enabled():
        return text
    parts: list[str] = []
    for ch in text:
        t = apply_char_rules(ch, options)
        if t is None:
            continue
        if options.unify_dashes and t == "-" and parts and parts[-1] == "-":
            continue
        parts.append(t)
    return "".join(parts)


def color_to_hex(color: int) -> str:
    return f"#{color & 0xFFFFFF:06X}"


def parse_hex_color(s: str) -> int | None:
    s = s.strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return int(s, 16)
    except ValueError:
        return None
