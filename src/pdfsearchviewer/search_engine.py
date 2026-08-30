from __future__ import annotations

import re
from collections import Counter

from .models import (
    BBox,
    CharInfo,
    DocumentIndex,
    Hit,
    SearchQuery,
    StyleFilter,
    strip_font_subset,
)
from .normalize import (
    build_normalized_stream,
    effective_normalize,
    trim_pattern_whitespace,
    normalize_display_text,
)
from .regex_locale import expand_locale_escapes


def _bbox_union(chars: list[CharInfo]) -> BBox:
    return (
        min(c.bbox[0] for c in chars),
        min(c.bbox[1] for c in chars),
        max(c.bbox[2] for c in chars),
        max(c.bbox[3] for c in chars),
    )


def hit_passes_presentation_filters(
    hit: Hit,
    style: StyleFilter,
    page_from: int | None = None,
    page_to: int | None = None,
) -> bool:
    """Style / region / page range — presentation only (not used during search)."""
    if page_from is not None and hit.page < page_from:
        return False
    if page_to is not None and hit.page > page_to:
        return False
    if style.is_empty():
        return True
    if style.fonts:
        name = strip_font_subset(hit.font).lower()
        if not any(f.lower() in name or name in f.lower() for f in style.fonts):
            return False
    if style.size_min is not None and hit.size + style.size_tolerance < style.size_min:
        return False
    if style.size_max is not None and hit.size - style.size_tolerance > style.size_max:
        return False
    if style.colors and hit.color not in style.colors:
        return False
    if style.region is not None:
        cx = (hit.bbox[0] + hit.bbox[2]) / 2
        cy = (hit.bbox[1] + hit.bbox[3]) / 2
        r = style.region
        if not (r[0] <= cx <= r[2] and r[1] <= cy <= r[3]):
            return False
    return True


def filter_hits(
    hits: list[Hit],
    style: StyleFilter | None = None,
    page_from: int | None = None,
    page_to: int | None = None,
) -> list[Hit]:
    style = style or StyleFilter()
    return [
        h
        for h in hits
        if hit_passes_presentation_filters(h, style, page_from, page_to)
    ]


def _dominant_style(chars: list[CharInfo]) -> tuple[str, float, int]:
    printable = [c for c in chars if not c.text.isspace()] or chars
    fonts = Counter(c.font for c in printable)
    sizes = Counter(round(c.size, 2) for c in printable)
    colors = Counter(c.color for c in printable)
    font = fonts.most_common(1)[0][0]
    size = sizes.most_common(1)[0][0]
    color = colors.most_common(1)[0][0]
    return font, float(size), color


def _pattern_for_search(pattern: str, options) -> str:
    """Apply the same whitespace ignoring to the query as to page text."""
    if not options.strip_whitespace:
        return pattern
    return trim_pattern_whitespace(pattern)


def _apply_whole_word(pattern: str) -> str:
    """Require ASCII word boundaries on both sides.

    Latin/ids: a substring inside a longer token will not match.
    CJK is not treated as a word-char here, so Chinese terms still match
    inside continuous Han text.
    """
    return rf"(?<![A-Za-z0-9_])(?:{pattern})(?![A-Za-z0-9_])"


def search(index: DocumentIndex, query: SearchQuery) -> list[Hit]:
    """Text search only. Style / region / page filters are applied at presentation time."""
    if not query.pattern:
        return []

    opts = effective_normalize(query.normalize, dotall=query.dotall)
    search_text, norm_to_stream = build_normalized_stream(
        index.raw_text, index.stream_map, opts
    )

    flags = 0
    if query.case_insensitive:
        flags |= re.IGNORECASE
    # Soft line-breaks are removed in the search stream; do not use re.DOTALL
    # so '.' / '.*' still stop at blank lines (kept as a single newline).

    pattern = _pattern_for_search(query.pattern, opts)
    if not pattern:
        return []

    if query.is_regex:
        try:
            body = expand_locale_escapes(pattern)
        except ValueError as e:
            raise ValueError(f"无效正则表达式: {e}") from e
    else:
        body = re.escape(pattern)
    if query.whole_word:
        body = _apply_whole_word(body)

    try:
        cre = re.compile(body, flags)
    except re.error as e:
        raise ValueError(f"无效正则表达式: {e}") from e

    hits: list[Hit] = []
    hit_id = 0

    for m in cre.finditer(search_text):
        if m.start() == m.end():
            continue
        # map normalized [start, end) -> stream indices -> char indices
        stream_indices = norm_to_stream[m.start() : m.end()]
        char_indices = [
            index.stream_map[si]
            for si in stream_indices
            if 0 <= si < len(index.stream_map) and index.stream_map[si] >= 0
        ]
        if not char_indices:
            continue

        char_start = min(char_indices)
        char_end = max(char_indices) + 1
        hit_chars = index.chars[char_start:char_end]
        if not hit_chars:
            continue

        page = hit_chars[0].page
        # multi-page hit: keep if majority on one page; use first page chars only for bbox
        page_chars = [c for c in hit_chars if c.page == page]
        if not page_chars:
            continue

        original = "".join(c.text for c in page_chars)
        # If match spanned inserted newlines, still show original from chars
        if not original:
            original = m.group(0)

        normalized = normalize_display_text(original, opts)
        font, size, color = _dominant_style(page_chars)

        hits.append(
            Hit(
                hit_id=hit_id,
                page=page,
                text=original,
                normalized_text=normalized,
                bbox=_bbox_union(page_chars),
                char_start=char_start,
                char_end=char_end,
                font=font,
                size=size,
                color=color,
            )
        )
        hit_id += 1

    return hits
