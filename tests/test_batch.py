from __future__ import annotations

from pathlib import Path

import pytest

from pdfsearchviewer.batch import (
    BatchLineResult,
    PatternFileError,
    apply_batch_session,
    batch_session_from_json,
    batch_session_to_json,
    capture_batch_session,
    flatten_batch_hits,
    format_batch_label,
    load_pattern_lines,
    run_batch,
    summarize_batch,
)
from pdfsearchviewer.cache import IndexCache
from pdfsearchviewer.models import (
    CharInfo,
    DocumentIndex,
    Hit,
    SearchQuery,
)


def _index_with_text(text: str) -> DocumentIndex:
    chars = [
        CharInfo(
            text=ch,
            font="helv",
            size=12.0,
            color=0,
            bbox=(float(i), 0.0, float(i + 1), 10.0),
            page=0,
            block=0,
            line=0,
            span=0,
            char_index=i,
        )
        for i, ch in enumerate(text)
        if ch != "\n"
    ]
    # Keep newlines in the stream so the search text matches the source.
    stream_map = []
    char_i = 0
    for ch in text:
        if ch == "\n":
            stream_map.append(-1)
        else:
            stream_map.append(char_i)
            char_i += 1
    return DocumentIndex(
        path="mem",
        fingerprint="mem",
        page_count=1,
        page_sizes=[(200.0, 200.0)],
        chars=chars,
        spans=[],
        raw_text=text,
        stream_map=stream_map,
    )


def test_skips_blank_lines_and_keeps_spaces(tmp_path: Path):
    path = tmp_path / "q.txt"
    path.write_text("\n  图 1 \r\n\n# keep\n", encoding="utf-8", newline="\n")
    assert load_pattern_lines(path) == [(2, "  图 1 "), (4, "# keep")]


def test_utf8_bom_and_utf16(tmp_path: Path):
    utf8 = tmp_path / "bom.txt"
    utf8.write_bytes("甲\n乙\n".encode("utf-8-sig"))
    assert load_pattern_lines(utf8) == [(1, "甲"), (2, "乙")]

    utf16 = tmp_path / "wide.txt"
    utf16.write_text("甲\n乙\n", encoding="utf-16")
    assert load_pattern_lines(utf16) == [(1, "甲"), (2, "乙")]


def test_gb18030(tmp_path: Path):
    path = tmp_path / "gb.txt"
    # 「图」in GB18030 is CD BC, which is also valid UTF-8 (U+037C).
    path.write_bytes("图1-2\n\nFigure\n".encode("gb18030"))
    assert load_pattern_lines(path) == [(1, "图1-2"), (3, "Figure")]


def test_utf8_chinese_without_bom(tmp_path: Path):
    path = tmp_path / "utf8.txt"
    path.write_bytes("图1-2\n".encode("utf-8"))
    assert load_pattern_lines(path) == [(1, "图1-2")]


def test_missing_file(tmp_path: Path):
    with pytest.raises(PatternFileError):
        load_pattern_lines(tmp_path / "nope.txt")


def test_batch_uses_template_flags_not_the_box_pattern():
    index = _index_with_text("cat catalog")
    lines = [(1, "cat"), (3, "catalog")]
    literal = SearchQuery(pattern="ignored", is_regex=False, whole_word=True)
    hits = run_batch(index, literal, lines)
    assert [len(item.hits) for item in hits] == [1, 1]
    assert hits[0].line_no == 1
    assert hits[0].hits[0].text == "cat"

    loose = SearchQuery(pattern="ignored", is_regex=False, whole_word=False)
    loose_hits = run_batch(index, loose, [(1, "cat")])
    assert len(loose_hits[0].hits) == 2


def test_invalid_regex_does_not_abort_later_lines():
    index = _index_with_text("axb")
    template = SearchQuery(pattern="ignored", is_regex=True)
    results = run_batch(index, template, [(2, "["), (4, "a.b")])
    assert results[0].error
    assert results[0].hits == []
    assert len(results[1].hits) == 1
    assert results[1].hits[0].text == "axb"


def test_cancel_stops_before_the_rejected_line():
    index = _index_with_text("ab")

    def on_progress(index_i: int, total: int, pattern: str) -> bool:
        return index_i < 1

    results = run_batch(
        index,
        SearchQuery(pattern="", is_regex=False),
        [(1, "a"), (2, "b")],
        on_progress=on_progress,
    )
    assert len(results) == 1
    assert results[0].pattern == "a"


def test_labels_and_summary():
    assert format_batch_label(12, "图 1-2", count=3, error=None) == "12: 图 1-2  （3）"
    assert format_batch_label(4, "[", count=None, error="bad") == "4: [  （无效）"
    long = "字" * 40
    label = format_batch_label(1, long, count=0, error=None)
    assert label.startswith("1: ")
    assert "…" in label
    assert label.endswith("（0）")

    rows = [
        BatchLineResult(1, "a", hits=[]),
        BatchLineResult(2, "[", error="bad"),
        BatchLineResult(3, "c", hits=[]),
    ]
    # pretend the third line has a visible hit
    title = summarize_batch(rows, [0, None, 2])
    assert title == "条目筛选 · 3 条 · 无命中 1 · 无效 1"


def test_flatten_is_one_search():
    def hit(text: str) -> Hit:
        return Hit(0, 0, text, text, (0.0, 0.0, 1.0, 1.0), 0, 1, "helv", 12.0, 0)

    first, second = hit("a"), hit("bb")
    results = [
        BatchLineResult(1, "a", hits=[first]),
        BatchLineResult(2, "[", error="bad"),
        BatchLineResult(4, "b", hits=[second]),
    ]
    hits, entry_of = flatten_batch_hits(results)
    assert [h.text for h in hits] == ["a", "bb"]
    assert [h.hit_id for h in hits] == [0, 1]
    assert entry_of == {0: 0, 1: 2}


def _saved_hit(hit_id: int, text: str) -> Hit:
    return Hit(hit_id, 0, text, text, (0.0, 0.0, 1.0, 1.0), 0, 1, "helv", 12.0, 0)


def test_batch_session_roundtrip():
    first, second = _saved_hit(0, "甲"), _saved_hit(1, "乙")
    results = [
        BatchLineResult(2, "甲", hits=[first]),
        BatchLineResult(5, "[", error="无效正则表达式: bad"),
        BatchLineResult(8, "乙", hits=[second]),
    ]
    session = capture_batch_session(
        results, [first, second], {0: 0, 1: 2}, {0}, r"D:\lists\terms.txt"
    )
    assert [entry.checked for entry in session.entries] == [True, False, False]
    assert session.entries[1].hit_ids == []
    restored = batch_session_from_json(batch_session_to_json(session))
    assert restored.path == session.path
    assert restored.entries[1].error == "无效正则表达式: bad"
    again, entry_of = apply_batch_session(restored, [first, second])
    assert [hit.text for hit in again[0].hits] == ["甲"]
    assert again[1].hits == []
    assert [hit.text for hit in again[2].hits] == ["乙"]
    assert entry_of == {0: 0, 1: 2}


def test_cache_stores_batch_and_migrates_old_db(tmp_path: Path):
    import sqlite3

    db = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL,
            name TEXT,
            pattern TEXT NOT NULL,
            query_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    cache = IndexCache(db)
    plain = cache.save_search("fp", SearchQuery(pattern="x", is_regex=False), [], name="plain")
    assert cache.load_batch(plain) is None

    hits = [_saved_hit(0, "甲")]
    session = capture_batch_session(
        [BatchLineResult(1, "甲", hits=hits)],
        hits,
        {0: 0},
        {0},
        str(tmp_path / "q.txt"),
    )
    sid = cache.save_search(
        "fp",
        SearchQuery(pattern="", is_regex=False),
        hits,
        name="q",
        batch_json=batch_session_to_json(session),
    )
    loaded = cache.load_batch(sid)
    assert loaded is not None
    assert loaded.entries[0].pattern == "甲"
    assert loaded.entries[0].checked is True
    assert cache.load_hits(sid)[0].text == "甲"
    cache.close()
