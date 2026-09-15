"""SQLite persistence for runs, drafts, evaluations and reviewer feedback."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,              -- running | completed | failed
    topic_area TEXT,
    topic_title TEXT,
    research_json TEXT,
    error TEXT,
    usage_json TEXT
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    is_final INTEGER NOT NULL DEFAULT 0,
    draft_json TEXT NOT NULL,
    rendered TEXT NOT NULL,
    eval_json TEXT,
    overall REAL
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL UNIQUE REFERENCES drafts(id),
    created_at TEXT NOT NULL,
    decision TEXT NOT NULL,            -- approved | edited | rejected
    final_text TEXT,
    reason TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class DraftRow:
    id: int
    run_id: int
    created_at: str
    revision: int
    is_final: bool
    draft: dict[str, Any]
    rendered: str
    evaluation: dict[str, Any] | None
    overall: float | None
    topic_area: str | None
    topic_title: str | None
    decision: str | None
    final_text: str | None
    reason: str | None


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ---- runs -------------------------------------------------------------

    def create_run(self) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (created_at, status) VALUES (?, 'running')", (_now(),)
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def set_run_topic(self, run_id: int, area: str, title: str) -> None:
        self.conn.execute(
            "UPDATE runs SET topic_area=?, topic_title=? WHERE id=?", (area, title, run_id)
        )
        self.conn.commit()

    def set_run_research(self, run_id: int, research: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE runs SET research_json=? WHERE id=?", (json.dumps(research), run_id)
        )
        self.conn.commit()

    def finish_run(self, run_id: int, usage: dict[str, Any], error: str | None = None) -> None:
        status = "failed" if error else "completed"
        self.conn.execute(
            "UPDATE runs SET status=?, error=?, usage_json=? WHERE id=?",
            (status, error, json.dumps(usage), run_id),
        )
        self.conn.commit()

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def recent_topics(self, days: int) -> list[str]:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
        rows = self.conn.execute(
            "SELECT topic_title FROM runs WHERE created_at >= ? AND topic_title IS NOT NULL",
            (since,),
        ).fetchall()
        return [r["topic_title"] for r in rows]

    # ---- drafts -----------------------------------------------------------

    def add_draft(
        self,
        run_id: int,
        revision: int,
        draft: dict[str, Any],
        rendered: str,
        evaluation: dict[str, Any] | None,
        overall: float | None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO drafts (run_id, created_at, revision, draft_json, rendered, eval_json,"
            " overall) VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                _now(),
                revision,
                json.dumps(draft),
                rendered,
                json.dumps(evaluation) if evaluation else None,
                overall,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def mark_final(self, draft_id: int) -> None:
        self.conn.execute("UPDATE drafts SET is_final=1 WHERE id=?", (draft_id,))
        self.conn.commit()

    def _draft_query(self, where: str, params: tuple[Any, ...]) -> list[DraftRow]:
        select = (
            "SELECT d.*, r.topic_area, r.topic_title, v.decision, v.final_text, v.reason"
            " FROM drafts d JOIN runs r ON r.id = d.run_id"
            " LEFT JOIN reviews v ON v.draft_id = d.id"
        )
        # `where` is always a literal defined in this class; values go through `params`.
        sql = f"{select} WHERE {where} ORDER BY d.created_at DESC, d.id DESC"
        return [self._to_row(r) for r in self.conn.execute(sql, params).fetchall()]

    @staticmethod
    def _to_row(r: sqlite3.Row) -> DraftRow:
        return DraftRow(
            id=r["id"],
            run_id=r["run_id"],
            created_at=r["created_at"],
            revision=r["revision"],
            is_final=bool(r["is_final"]),
            draft=json.loads(r["draft_json"]),
            rendered=r["rendered"],
            evaluation=json.loads(r["eval_json"]) if r["eval_json"] else None,
            overall=r["overall"],
            topic_area=r["topic_area"],
            topic_title=r["topic_title"],
            decision=r["decision"],
            final_text=r["final_text"],
            reason=r["reason"],
        )

    def get_draft(self, draft_id: int) -> DraftRow | None:
        rows = self._draft_query("d.id = ?", (draft_id,))
        return rows[0] if rows else None

    def list_final_drafts(self, decision: str | None = None) -> list[DraftRow]:
        if decision == "pending":
            return self._draft_query("d.is_final = 1 AND v.id IS NULL", ())
        if decision:
            return self._draft_query("d.is_final = 1 AND v.decision = ?", (decision,))
        return self._draft_query("d.is_final = 1", ())

    def drafts_for_run(self, run_id: int) -> list[DraftRow]:
        return self._draft_query("d.run_id = ?", (run_id,))

    # ---- reviews ----------------------------------------------------------

    def add_review(
        self, draft_id: int, decision: str, final_text: str | None, reason: str | None
    ) -> None:
        self.conn.execute(
            "INSERT INTO reviews (draft_id, created_at, decision, final_text, reason)"
            " VALUES (?,?,?,?,?) ON CONFLICT(draft_id) DO UPDATE SET"
            " created_at=excluded.created_at, decision=excluded.decision,"
            " final_text=excluded.final_text, reason=excluded.reason",
            (draft_id, _now(), decision, final_text, reason),
        )
        self.conn.commit()

    def recent_feedback(self, limit: int) -> list[DraftRow]:
        """Edited and rejected drafts, newest first (the signal the voice profile learns from)."""
        rows = self._draft_query("v.decision IN ('edited', 'rejected')", ())
        return rows[:limit]
