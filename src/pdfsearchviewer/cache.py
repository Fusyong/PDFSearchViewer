from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import (
    CharInfo,
    DocumentIndex,
    Hit,
    NormalizeOptions,
    SearchQuery,
    SpanInfo,
    StyleFilter,
    StyleMatchMode,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    fingerprint TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    indexed_at REAL NOT NULL,
    index_blob BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    name TEXT,
    pattern TEXT NOT NULL,
    query_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (fingerprint) REFERENCES documents(fingerprint)
);

CREATE TABLE IF NOT EXISTS hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL,
    hit_id INTEGER NOT NULL,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    bbox_json TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    font TEXT NOT NULL,
    size REAL NOT NULL,
    color INTEGER NOT NULL,
    reviewed INTEGER,
    FOREIGN KEY (search_id) REFERENCES searches(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_searches_fp ON searches(fingerprint);
CREATE INDEX IF NOT EXISTS idx_hits_search ON hits(search_id);
"""


def _default_db_path() -> Path:
    base = Path.home() / ".pdfsearchviewer"
    base.mkdir(parents=True, exist_ok=True)
    return base / "cache.sqlite3"


class IndexCache:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def get_index(self, fingerprint: str) -> DocumentIndex | None:
        row = self._conn.execute(
            "SELECT index_blob FROM documents WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if not row:
            return None
        return _deserialize_index(row["index_blob"])

    def put_index(self, index: DocumentIndex) -> None:
        import time

        blob = _serialize_index(index)
        self._conn.execute(
            """
            INSERT INTO documents (fingerprint, path, page_count, indexed_at, index_blob)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET
                path=excluded.path,
                page_count=excluded.page_count,
                indexed_at=excluded.indexed_at,
                index_blob=excluded.index_blob
            """,
            (index.fingerprint, index.path, index.page_count, time.time(), blob),
        )
        self._conn.commit()

    def save_search(
        self,
        fingerprint: str,
        query: SearchQuery,
        hits: list[Hit],
        name: str | None = None,
    ) -> int:
        import time

        qj = _query_to_json(query)
        cur = self._conn.execute(
            """
            INSERT INTO searches (fingerprint, name, pattern, query_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (fingerprint, name, query.pattern, qj, time.time()),
        )
        search_id = int(cur.lastrowid)
        for h in hits:
            self._conn.execute(
                """
                INSERT INTO hits (
                    search_id, hit_id, page, text, normalized_text, bbox_json,
                    char_start, char_end, font, size, color, reviewed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    search_id,
                    h.hit_id,
                    h.page,
                    h.text,
                    h.normalized_text,
                    json.dumps(list(h.bbox)),
                    h.char_start,
                    h.char_end,
                    h.font,
                    h.size,
                    h.color,
                    None if h.reviewed is None else (1 if h.reviewed else 0),
                ),
            )
        self._conn.commit()
        return search_id

    def list_searches(self, fingerprint: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, name, pattern, created_at,
                   (SELECT COUNT(*) FROM hits WHERE search_id = searches.id) AS hit_count
            FROM searches WHERE fingerprint = ? ORDER BY created_at DESC
            """,
            (fingerprint,),
        ).fetchall()
        return [dict(r) for r in rows]

    def load_hits(self, search_id: int) -> list[Hit]:
        rows = self._conn.execute(
            "SELECT * FROM hits WHERE search_id = ? ORDER BY hit_id",
            (search_id,),
        ).fetchall()
        hits: list[Hit] = []
        for r in rows:
            reviewed = r["reviewed"]
            hits.append(
                Hit(
                    hit_id=r["hit_id"],
                    page=r["page"],
                    text=r["text"],
                    normalized_text=r["normalized_text"],
                    bbox=tuple(json.loads(r["bbox_json"])),  # type: ignore[arg-type]
                    char_start=r["char_start"],
                    char_end=r["char_end"],
                    font=r["font"],
                    size=r["size"],
                    color=r["color"],
                    reviewed=None if reviewed is None else bool(reviewed),
                )
            )
        return hits

    def update_hit_review(self, search_id: int, hit_id: int, reviewed: bool | None) -> None:
        val = None if reviewed is None else (1 if reviewed else 0)
        self._conn.execute(
            "UPDATE hits SET reviewed = ? WHERE search_id = ? AND hit_id = ?",
            (val, search_id, hit_id),
        )
        self._conn.commit()

    def load_query(self, search_id: int) -> SearchQuery | None:
        row = self._conn.execute(
            "SELECT query_json FROM searches WHERE id = ?", (search_id,)
        ).fetchone()
        if not row:
            return None
        return _query_from_json(row["query_json"])


def _serialize_index(index: DocumentIndex) -> bytes:
    payload = {
        "path": index.path,
        "fingerprint": index.fingerprint,
        "page_count": index.page_count,
        "page_sizes": index.page_sizes,
        "raw_text": index.raw_text,
        "stream_map": index.stream_map,
        "chars": [
            {
                "text": c.text,
                "font": c.font,
                "size": c.size,
                "color": c.color,
                "bbox": list(c.bbox),
                "page": c.page,
                "block": c.block,
                "line": c.line,
                "span": c.span,
                "char_index": c.char_index,
            }
            for c in index.chars
        ],
        "spans": [
            {
                "text": s.text,
                "font": s.font,
                "size": s.size,
                "color": s.color,
                "bbox": list(s.bbox),
                "page": s.page,
                "block": s.block,
                "line": s.line,
                "span": s.span,
                "char_start": s.char_start,
                "char_end": s.char_end,
            }
            for s in index.spans
        ],
    }
    return gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"), compresslevel=6)


def _deserialize_index(blob: bytes) -> DocumentIndex:
    payload = json.loads(gzip.decompress(blob).decode("utf-8"))
    chars = [
        CharInfo(
            text=c["text"],
            font=c["font"],
            size=c["size"],
            color=c["color"],
            bbox=tuple(c["bbox"]),  # type: ignore[arg-type]
            page=c["page"],
            block=c["block"],
            line=c["line"],
            span=c["span"],
            char_index=c["char_index"],
        )
        for c in payload["chars"]
    ]
    spans = [
        SpanInfo(
            text=s["text"],
            font=s["font"],
            size=s["size"],
            color=s["color"],
            bbox=tuple(s["bbox"]),  # type: ignore[arg-type]
            page=s["page"],
            block=s["block"],
            line=s["line"],
            span=s["span"],
            char_start=s["char_start"],
            char_end=s["char_end"],
        )
        for s in payload["spans"]
    ]
    return DocumentIndex(
        path=payload["path"],
        fingerprint=payload["fingerprint"],
        page_count=payload["page_count"],
        page_sizes=[tuple(ps) for ps in payload["page_sizes"]],  # type: ignore[misc]
        chars=chars,
        spans=spans,
        raw_text=payload["raw_text"],
        stream_map=payload["stream_map"],
    )


def _query_to_json(query: SearchQuery) -> str:
    return json.dumps(
        {
            "pattern": query.pattern,
            "is_regex": query.is_regex,
            "case_insensitive": query.case_insensitive,
            "dotall": query.dotall,
            "normalize": {
                "strip_whitespace": query.normalize.strip_whitespace,
                "unify_digits": query.normalize.unify_digits,
                "unify_dashes": query.normalize.unify_dashes,
            },
            "style": {
                "fonts": query.style.fonts,
                "size_min": query.style.size_min,
                "size_max": query.style.size_max,
                "size_tolerance": query.style.size_tolerance,
                "colors": query.style.colors,
                "region": list(query.style.region) if query.style.region else None,
                "match_mode": query.style.match_mode.value,
            },
            "page_from": query.page_from,
            "page_to": query.page_to,
        },
        ensure_ascii=False,
    )


def _query_from_json(s: str) -> SearchQuery:
    d = json.loads(s)
    n = d.get("normalize", {})
    st = d.get("style", {})
    region = st.get("region")
    return SearchQuery(
        pattern=d["pattern"],
        is_regex=d.get("is_regex", True),
        case_insensitive=d.get("case_insensitive", False),
        dotall=d.get("dotall", False),
        normalize=NormalizeOptions(
            strip_whitespace=n.get("strip_whitespace", False),
            unify_digits=n.get("unify_digits", False),
            unify_dashes=n.get("unify_dashes", False),
        ),
        style=StyleFilter(
            fonts=st.get("fonts", []),
            size_min=st.get("size_min"),
            size_max=st.get("size_max"),
            size_tolerance=st.get("size_tolerance", 0.1),
            colors=st.get("colors", []),
            region=tuple(region) if region else None,  # type: ignore[arg-type]
            match_mode=StyleMatchMode(st.get("match_mode", "majority")),
        ),
        page_from=d.get("page_from"),
        page_to=d.get("page_to"),
    )
