"""Read-only summaries for the dashboard: pending count, recent runs, token usage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from postgen.store.db import Store


@dataclass
class UsageTotals:
    runs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0


@dataclass
class RunSummary:
    id: int
    created_at: str
    status: str
    topic_title: str | None
    error: str | None
    draft_id: int | None
    decision: str | None


def pending_count(store: Store) -> int:
    row = store.one(
        "SELECT COUNT(*) AS n FROM drafts d LEFT JOIN reviews v ON v.draft_id = d.id"
        " WHERE d.is_final = 1 AND v.id IS NULL"
    )
    return int(row["n"]) if row else 0


def usage_totals(store: Store) -> UsageTotals:
    totals = UsageTotals()
    for row in store.rows("SELECT usage_json FROM runs WHERE usage_json IS NOT NULL"):
        usage: dict[str, Any] = json.loads(row["usage_json"]) or {}
        totals.runs += 1
        totals.input_tokens += int(usage.get("input_tokens", 0))
        totals.output_tokens += int(usage.get("output_tokens", 0))
        totals.cache_read += int(usage.get("cache_read", 0))
        totals.cache_write += int(usage.get("cache_write", 0))
    return totals


def recent_runs(store: Store, limit: int = 10) -> list[RunSummary]:
    rows = store.rows(
        "SELECT r.id, r.created_at, r.status, r.topic_title, r.error, d.id AS draft_id,"
        " v.decision FROM runs r"
        " LEFT JOIN drafts d ON d.run_id = r.id AND d.is_final = 1"
        " LEFT JOIN reviews v ON v.draft_id = d.id"
        " ORDER BY r.id DESC LIMIT ?",
        (limit,),
    )
    return [
        RunSummary(
            id=r["id"],
            created_at=r["created_at"],
            status=r["status"],
            topic_title=r["topic_title"],
            error=r["error"],
            draft_id=r["draft_id"],
            decision=r["decision"],
        )
        for r in rows
    ]
