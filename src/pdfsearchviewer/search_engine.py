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
    StyleMatchMode,
    strip_font_subset,
)
from .normalize import build_normalized_stream, normalize_display_text


def _bbox_union(chars: list[CharInfo]) -> BBox:
    return (
        min(c.bbox[0] for c in chars),
        min(c.bbox[1] for c in chars),
        max(c.bbox[2] for c in chars),
        max(c.bbox[3] for c in chars),
    )


def _char_in_region(ch: CharInfo, region: BBox) -> bool:
    cx = (ch.bbox[0] + ch.bbox[2]) / 2
    cy = (ch.bbox[1] + ch.bbox[3]) / 2
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


def _style_match_char(ch: CharInfo, style: StyleFilter) -> bool:
    if style.fonts:
        name = strip_font_subset(ch.font).lower()
        if not any(f.lower() in name or name in f.lower() for f in style.fonts):
            return False
    if style.size_min is not None and ch.size + style.size_tolerance < style.size_min:
        return False
    if style.size_max is not None and ch.size - style.size_tolerance > style.size_max:
        return False
    if style.colors and ch.color not in style.colors:
        return False
    if style.region is not None and not _char_in_region(ch, style.region):
        return False
    return True


def _hit_passes_style(chars: list[CharInfo], style: StyleFilter) -> bool:
    if style.is_empty() or not chars:
        return True
    flags = [_style_match_char(c, style) for c in chars]
    mode = style.match_mode
    if mode == StyleMatchMode.ALL:
        return all(flags)
    if mode == StyleMatchMode.ANY:
        return any(flags)
    if mode == StyleMatchMode.FIRST_SPAN:
        # first non-whitespace char
        for c in chars:
            if not c.text.isspace():
                return _style_match_char(c, style)
        return _style_match_char(chars[0], style)
    # majority
    return sum(flags) * 2 >= len(flags)


def _dominant_style(chars: list[CharInfo]) -> tuple[str, float, int]:
    printable = [c for c in chars if not c.text.isspace()] or chars
    fonts = Counter(c.font for c in printable)
    sizes = Counter(round(c.size, 2) for c in printable)
    colors = Counter(c.color for c in printable)
    font = fonts.most_common(1)[0][0]
    size = sizes.most_common(1)[0][0]
    color = colors.most_common(1)[0][0]
    return font, float(size), color


def search(index: DocumentIndex, query: SearchQuery) -> list[Hit]:
    if not query.pattern:
        return []

    search_text, norm_to_stream = build_normalized_stream(
        index.raw_text, index.stream_map, query.normalize
    )

    flags = 0
    if query.case_insensitive:
        flags |= re.IGNORECASE
    if query.dotall:
        flags |= re.DOTALL

    if query.is_regex:
        try:
            cre = re.compile(query.pattern, flags)
        except re.error as e:
            raise ValueError(f"无效正则表达式: {e}") from e
    else:
        cre = re.compile(re.escape(query.pattern), flags)

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

        # page filter
        page = hit_chars[0].page
        if query.page_from is not None and page < query.page_from:
            continue
        if query.page_to is not None and page > query.page_to:
            continue

        # multi-page hit: keep if majority on one page; use first page chars only for bbox
        page_chars = [c for c in hit_chars if c.page == page]
        if not page_chars:
            continue

        if not _hit_passes_style(page_chars, query.style):
            continue

        original = "".join(c.text for c in page_chars)
        # If match spanned inserted newlines, still show original from chars
        if not original:
            original = m.group(0)

        normalized = normalize_display_text(original, query.normalize)
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
