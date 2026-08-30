from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf

from .models import BBox, CharInfo, DocumentIndex, SpanInfo


def file_fingerprint(path: str | Path) -> str:
    p = Path(path)
    st = p.stat()
    h = hashlib.sha256()
    h.update(str(p.resolve()).encode("utf-8", errors="replace"))
    h.update(str(st.st_mtime_ns).encode())
    h.update(str(st.st_size).encode())
    # sample file head/tail for stronger identity without full hash of huge PDFs
    with p.open("rb") as f:
        head = f.read(65536)
        h.update(head)
        if st.st_size > 65536:
            f.seek(max(0, st.st_size - 65536))
            h.update(f.read(65536))
    return h.hexdigest()


def _union_bbox(boxes: list[BBox]) -> BBox:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def index_pdf(path: str | Path, progress=None) -> DocumentIndex:
    """Extract character-level index with style metadata."""
    path = Path(path)
    fp = file_fingerprint(path)
    doc = pymupdf.open(path)
    try:
        chars: list[CharInfo] = []
        spans: list[SpanInfo] = []
        page_sizes: list[tuple[float, float]] = []
        raw_parts: list[str] = []
        stream_map: list[int] = []

        for page_no in range(len(doc)):
            if progress:
                progress(page_no + 1, len(doc))
            page = doc[page_no]
            page_sizes.append((page.rect.width, page.rect.height))
            data = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_TEXT)

            first_line_on_page = True
            for bi, block in enumerate(data.get("blocks", [])):
                if block.get("type", 0) != 0:
                    continue
                for li, line in enumerate(block.get("lines", [])):
                    if not first_line_on_page:
                        raw_parts.append("\n")
                        stream_map.append(-1)
                    first_line_on_page = False

                    for si, span in enumerate(line.get("spans", [])):
                        font = span.get("font", "")
                        size = float(span.get("size", 0))
                        color = int(span.get("color", 0))
                        span_char_start = len(chars)
                        span_boxes: list[BBox] = []
                        span_text_parts: list[str] = []

                        for ch in span.get("chars", []):
                            c = ch.get("c", "")
                            if c == "":
                                continue
                            bbox = tuple(ch.get("bbox", (0, 0, 0, 0)))
                            info = CharInfo(
                                text=c,
                                font=font,
                                size=size,
                                color=color,
                                bbox=bbox,  # type: ignore[arg-type]
                                page=page_no,
                                block=bi,
                                line=li,
                                span=si,
                                char_index=len(chars),
                            )
                            chars.append(info)
                            raw_parts.append(c)
                            stream_map.append(info.char_index)
                            span_text_parts.append(c)
                            span_boxes.append(info.bbox)

                        if span_text_parts:
                            spans.append(
                                SpanInfo(
                                    text="".join(span_text_parts),
                                    font=font,
                                    size=size,
                                    color=color,
                                    bbox=_union_bbox(span_boxes),
                                    page=page_no,
                                    block=bi,
                                    line=li,
                                    span=si,
                                    char_start=span_char_start,
                                    char_end=len(chars),
                                )
                            )

            # Page separator: two newlines so collapse_single_newlines keeps a barrier
            if page_no < len(doc) - 1 and raw_parts:
                raw_parts.append("\n\n")
                stream_map.append(-1)
                stream_map.append(-1)

        return DocumentIndex(
            path=str(path.resolve()),
            fingerprint=fp,
            page_count=len(doc),
            page_sizes=page_sizes,
            chars=chars,
            spans=spans,
            raw_text="".join(raw_parts),
            stream_map=stream_map,
        )
    finally:
        doc.close()
