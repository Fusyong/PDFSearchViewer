"""Display page ↔ PDF physical page conversion.

Internal storage uses 0-based PDF page indices.
Users see and enter display pages: ``display = pdf_0based + 1 + offset``.
``offset`` is an integer (may be negative) to align with book pagination.
"""

from __future__ import annotations


def to_display_page(pdf_page_0based: int, offset: int = 0) -> int:
    """Convert 0-based PDF page to user-facing book page number."""
    return pdf_page_0based + 1 + offset


def to_pdf_page(display_page: int, offset: int = 0) -> int:
    """Convert user-facing book page number to 0-based PDF page."""
    return display_page - 1 - offset


def spread_left_page(display_page: int) -> int:
    """Even (verso) page number on the left of the spread containing ``display_page``.

    Chinese book convention: even pages on the left, odd (= left + 1) on the right.
    Page 1 sits alone on the right with an empty left (left key 0).
    """
    if display_page % 2 == 0:
        return display_page
    return display_page - 1


def spread_right_page(left_page: int) -> int:
    """Odd (recto) page paired with an even left page (or 0 → 1)."""
    return left_page + 1
