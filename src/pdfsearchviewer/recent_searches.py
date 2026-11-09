"""最近使用的搜索式。最新的在最前，与具体 PDF 无关。"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_LIMIT = 30
_VERSION = 1


def default_recent_path() -> Path:
    """与索引缓存同一目录：%USERPROFILE%\\.pdfsearchviewer\\"""
    return Path.home() / ".pdfsearchviewer" / "recent_searches.json"


def load_recent(path: Path, *, limit: int = DEFAULT_LIMIT) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    patterns = data.get("patterns") if isinstance(data, dict) else None
    if not isinstance(patterns, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in patterns:
        if not isinstance(item, str) or item == "" or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def save_recent(path: Path, patterns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"version": _VERSION, "patterns": patterns},
        ensure_ascii=False,
        indent=2,
    )
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload + "\n", encoding="utf-8")
    tmp.replace(path)


def promote(patterns: list[str], text: str, *, limit: int = DEFAULT_LIMIT) -> list[str] | None:
    """把 ``text`` 放到最前。空字符串不记。没有变化时返回 None。"""
    if text == "":
        return None
    updated = [text, *[item for item in patterns if item != text]]
    if limit >= 0:
        updated = updated[:limit]
    if updated == patterns:
        return None
    return updated


class RecentSearches:
    def __init__(self, path: Path, *, limit: int = DEFAULT_LIMIT):
        self.path = Path(path)
        self.limit = limit
        self.patterns = load_recent(self.path, limit=limit)

    def remember(self, text: str) -> list[str] | None:
        """记住一次搜索。列表未变时返回 None，且不写盘。"""
        updated = promote(self.patterns, text, limit=self.limit)
        if updated is None:
            return None
        self.patterns = updated
        try:
            save_recent(self.path, self.patterns)
        except OSError:
            pass
        return list(self.patterns)
