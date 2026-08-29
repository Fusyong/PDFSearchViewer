from __future__ import annotations

from dataclasses import dataclass

from .models import Hit
from .normalize import color_to_hex


@dataclass
class StatGroup:
    key: str
    label: str
    count: int
    hit_ids: list[int]


def group_hits(hits: list[Hit], by: str) -> list[StatGroup]:
    """
    by: text | normalized | font | size | color
    """
    buckets: dict[str, list[int]] = {}
    labels: dict[str, str] = {}

    for h in hits:
        if by == "text":
            key = h.text
            label = repr(h.text) if h.text != h.text.strip() else h.text
        elif by == "normalized":
            key = h.normalized_text
            label = h.normalized_text
        elif by == "font":
            key = h.font_display
            label = h.font_display
        elif by == "size":
            key = f"{h.size:.2f}"
            label = f"{h.size:.2f} pt"
        elif by == "color":
            key = color_to_hex(h.color)
            label = key
        else:
            raise ValueError(f"unknown group by: {by}")
        buckets.setdefault(key, []).append(h.hit_id)
        labels[key] = label

    groups = [
        StatGroup(key=k, label=labels[k], count=len(ids), hit_ids=ids)
        for k, ids in buckets.items()
    ]
    groups.sort(key=lambda g: (-g.count, g.label))
    return groups


def summary_counts(hits: list[Hit]) -> dict[str, int]:
    return {
        "total": len(hits),
        "unique_text": len({h.text for h in hits}),
        "unique_normalized": len({h.normalized_text for h in hits}),
        "unique_font": len({h.font_display for h in hits}),
        "unique_size": len({round(h.size, 2) for h in hits}),
        "unique_color": len({h.color for h in hits}),
        "reviewed_ok": sum(1 for h in hits if h.reviewed is True),
        "reviewed_bad": sum(1 for h in hits if h.reviewed is False),
        "unreviewed": sum(1 for h in hits if h.reviewed is None),
    }
