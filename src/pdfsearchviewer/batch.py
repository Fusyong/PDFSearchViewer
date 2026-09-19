"""Line-oriented batch search: one pattern per line, shared search options."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from .models import DocumentIndex, Hit, SearchQuery
from .search_engine import search


class PatternFileError(ValueError):
    """The pattern list could not be read or decoded."""


@dataclass
class BatchLineResult:
    """One source line and the hits (or error) produced with the shared options."""

    line_no: int  # 1-based line in the source file
    pattern: str
    hits: list[Hit] = field(default_factory=list)
    error: str | None = None


@dataclass
class BatchEntryRecord:
    """One saved filter row: the source line, its hits, and whether it is shown."""

    line_no: int
    pattern: str
    error: str | None = None
    checked: bool = True
    hit_ids: list[int] = field(default_factory=list)


@dataclass
class BatchSession:
    """Entry filter stored with a search so it can be opened again."""

    path: str | None = None
    entries: list[BatchEntryRecord] = field(default_factory=list)


def _cjk_count(text: str) -> int:
    """Han, CJK punctuation, and fullwidth forms — used only to break ties."""
    n = 0
    for ch in text:
        o = ord(ch)
        if (
            0x3400 <= o <= 0x4DBF
            or 0x4E00 <= o <= 0x9FFF
            or 0x3000 <= o <= 0x303F
            or 0xFF00 <= o <= 0xFFEF
        ):
            n += 1
    return n


def read_text_file(path: Path) -> str:
    """Read a pattern list saved by Windows editors.

    UTF-8 (with or without BOM) and UTF-16 BOM are detected first.
    If UTF-8 fails, fall back to GB18030.

    Some GB18030 bytes are also valid UTF-8 (for example「图」is ``CD BC``,
    which is U+037C in UTF-8). When both decoders succeed and disagree,
    prefer the one that yields more CJK characters, and keep UTF-8 when
    it already contains CJK.
    """
    try:
        data = path.read_bytes()
    except OSError as e:
        raise PatternFileError(f"无法读取文件：{e}") from e
    if not data:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        as_utf8 = data.decode("utf-8")
    except UnicodeDecodeError:
        as_utf8 = None
    try:
        as_gb = data.decode("gb18030")
    except UnicodeDecodeError:
        as_gb = None
    if as_utf8 is None and as_gb is None:
        raise PatternFileError(
            f"无法识别文件编码（请使用 UTF-8 或 GB18030）：{path.name}"
        )
    if as_utf8 is None:
        return as_gb or ""
    if as_gb is None or as_utf8 == as_gb:
        return as_utf8
    if _cjk_count(as_utf8) == 0 and _cjk_count(as_gb) > 0:
        return as_gb
    return as_utf8


def load_pattern_lines(path: str | Path) -> list[tuple[int, str]]:
    """Return (1-based line number, pattern) for each non-blank line.

    Line endings are removed. Other whitespace is kept, so it still
    participates in matching unless「忽略空白」is on. Blank lines are skipped.
    """
    path = Path(path)
    if not path.is_file():
        raise PatternFileError(f"找不到文件：{path}")
    text = read_text_file(path)
    lines: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.strip() == "":
            continue
        lines.append((line_no, line))
    return lines


def run_batch(
    index: DocumentIndex,
    template: SearchQuery,
    lines: list[tuple[int, str]],
    *,
    on_progress: Callable[[int, int, str], bool] | None = None,
) -> list[BatchLineResult]:
    """Search each line with ``template`` options, replacing only the pattern.

    ``on_progress(index, total, pattern)`` is called before each line.
    Return False from it to stop; results gathered so far are returned.
    An invalid pattern is recorded on that line and does not abort the rest.
    """
    total = len(lines)
    results: list[BatchLineResult] = []
    for index_i, (line_no, pattern) in enumerate(lines):
        if on_progress is not None and not on_progress(index_i, total, pattern):
            break
        query = replace(template, pattern=pattern)
        try:
            hits = search(index, query)
        except ValueError as e:
            results.append(
                BatchLineResult(line_no=line_no, pattern=pattern, error=str(e))
            )
            continue
        results.append(BatchLineResult(line_no=line_no, pattern=pattern, hits=hits))
    return results


def flatten_batch_hits(
    results: list[BatchLineResult],
) -> tuple[list[Hit], dict[int, int]]:
    """Merge every line into one hit list, as if it were a single search.

    Hit ids are renumbered from 0. The returned map is ``hit_id -> entry index``
    so the UI can show or hide a whole source line without a new search.
    """
    combined: list[Hit] = []
    entry_of: dict[int, int] = {}
    hit_id = 0
    for entry_index, entry in enumerate(results):
        for hit in entry.hits:
            hit.hit_id = hit_id
            combined.append(hit)
            entry_of[hit_id] = entry_index
            hit_id += 1
    return combined, entry_of


def capture_batch_session(
    results: list[BatchLineResult],
    hits: list[Hit],
    entry_of: dict[int, int],
    checked: set[int],
    path: str | None,
) -> BatchSession:
    """Snapshot the live entry filter, including which hits belong to each line."""
    buckets: dict[int, list[int]] = {i: [] for i in range(len(results))}
    for hit in hits:
        index = entry_of.get(hit.hit_id)
        if index is not None and index in buckets:
            buckets[index].append(hit.hit_id)
    entries = [
        BatchEntryRecord(
            line_no=entry.line_no,
            pattern=entry.pattern,
            error=entry.error,
            checked=i in checked,
            hit_ids=buckets[i],
        )
        for i, entry in enumerate(results)
    ]
    return BatchSession(path=path, entries=entries)


def batch_session_to_json(session: BatchSession) -> str:
    return json.dumps(
        {
            "path": session.path,
            "entries": [
                {
                    "line_no": entry.line_no,
                    "pattern": entry.pattern,
                    "error": entry.error,
                    "checked": entry.checked,
                    "hit_ids": entry.hit_ids,
                }
                for entry in session.entries
            ],
        },
        ensure_ascii=False,
    )


def batch_session_from_json(raw: str) -> BatchSession:
    data = json.loads(raw)
    entries: list[BatchEntryRecord] = []
    for item in data.get("entries") or []:
        entries.append(
            BatchEntryRecord(
                line_no=int(item["line_no"]),
                pattern=str(item.get("pattern", "")),
                error=item.get("error") or None,
                checked=bool(item.get("checked", True)),
                hit_ids=[int(hit_id) for hit_id in item.get("hit_ids") or []],
            )
        )
    path = data.get("path") or None
    return BatchSession(path=path, entries=entries)


def apply_batch_session(
    session: BatchSession,
    hits: list[Hit],
) -> tuple[list[BatchLineResult], dict[int, int]]:
    """Rebuild per-line hit groups from a saved filter and the flat hit list."""
    by_id = {hit.hit_id: hit for hit in hits}
    results: list[BatchLineResult] = []
    entry_of: dict[int, int] = {}
    for index, record in enumerate(session.entries):
        owned: list[Hit] = []
        for hit_id in record.hit_ids:
            hit = by_id.get(hit_id)
            if hit is None:
                continue
            owned.append(hit)
            entry_of[hit.hit_id] = index
        results.append(
            BatchLineResult(
                line_no=record.line_no,
                pattern=record.pattern,
                hits=owned,
                error=record.error,
            )
        )
    return results, entry_of


def format_batch_label(
    line_no: int,
    pattern: str,
    *,
    count: int | None,
    error: str | None,
) -> str:
    """Short list label: source line, pattern, and visible hit count."""
    shown = pattern.replace("\t", " ")
    if len(shown) > 32:
        shown = shown[:31] + "…"
    head = f"{line_no}: {shown}"
    if error:
        return f"{head}  （无效）"
    if count is None:
        return head
    return f"{head}  （{count}）"


def summarize_batch(
    results: list[BatchLineResult],
    visible_counts: list[int | None],
) -> str:
    """Group-box title: how many lines, how many show nothing, how many failed."""
    invalid = sum(1 for item in results if item.error)
    missed = sum(
        1
        for item, count in zip(results, visible_counts)
        if not item.error and count == 0
    )
    return f"条目筛选 · {len(results)} 条 · 无命中 {missed} · 无效 {invalid}"
