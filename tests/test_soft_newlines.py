from __future__ import annotations

from pdfsearchviewer.models import NormalizeOptions
from pdfsearchviewer.normalize import build_normalized_stream, effective_normalize


def test_collapse_single_newlines_joins_soft_wrap():
    raw = "学\n习\n\n其它"
    sm = list(range(len(raw)))
    text, mapping = build_normalized_stream(
        raw, sm, NormalizeOptions(collapse_single_newlines=True)
    )
    assert text == "学习\n其它"
    assert len(mapping) == len(text)


def test_collapse_via_legacy_dotall_flag():
    raw = "学\n习\n\n其它"
    sm = list(range(len(raw)))
    opts = effective_normalize(NormalizeOptions(), dotall=True)
    text, _ = build_normalized_stream(raw, sm, opts)
    assert text == "学习\n其它"


def test_without_collapse_keeps_newlines():
    raw = "学\n习\n\n其它"
    sm = list(range(len(raw)))
    text, _ = build_normalized_stream(raw, sm, NormalizeOptions())
    assert text == raw
