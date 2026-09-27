"""Small SQLite FTS5 indexer for local CST Online Help HTML."""

from __future__ import annotations

import os
import sqlite3
from html.parser import HTMLParser
from pathlib import Path

from cst_rf.errors import CSTRFError, ErrorCode


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.parts: list[str] = []
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "nav", "footer"}:
            self._skip += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "nav", "footer"} and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title += f" {text}"
        else:
            self.parts.append(text)


def _parse(path: Path, root: Path) -> tuple[str, str, str]:
    parser = _TextParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    title = " ".join(parser.title.split()) or path.stem
    text = " ".join(parser.parts)
    relative = path.relative_to(root).as_posix()
    return title, text, relative


class HelpIndex:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir.expanduser().resolve()
        self.database = self.output_dir / "cst-help.sqlite"

    def build(self, help_root: Path, *, limit: int | None = None) -> dict[str, int | str]:
        root = help_root.expanduser().resolve()
        if not root.is_dir():
            raise CSTRFError(ErrorCode.PROJECT_NOT_FOUND, f"help root does not exist: {root}")
        files = sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".htm", ".html"}
        )
        if limit is not None:
            files = files[:limit]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.database.with_suffix(".tmp.sqlite")
        temporary.unlink(missing_ok=True)
        connection = sqlite3.connect(temporary)
        try:
            connection.execute("CREATE VIRTUAL TABLE help USING fts5(title, path UNINDEXED, text)")
            rows = []
            for path in files:
                title, text, relative = _parse(path, root)
                if text:
                    rows.append((title, relative, text))
            connection.executemany("INSERT INTO help(title, path, text) VALUES (?, ?, ?)", rows)
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, self.database)
        return {"database": str(self.database), "files": len(files), "topics": len(rows)}

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, str]]:
        if not query.strip():
            raise CSTRFError(ErrorCode.INVALID_ARGUMENT, "query is required")
        if not self.database.is_file():
            raise CSTRFError(ErrorCode.RESULT_NOT_FOUND, "help index has not been built")
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT title, path, snippet(help, 2, '[', ']', '…', 32) AS snippet "
                "FROM help WHERE help MATCH ? ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise CSTRFError(ErrorCode.INVALID_ARGUMENT, f"invalid help query: {exc}") from exc
        finally:
            connection.close()
