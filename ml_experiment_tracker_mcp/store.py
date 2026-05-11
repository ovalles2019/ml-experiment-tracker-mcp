"""SQLite-backed persistence for experiments, metrics, and hyperparameters."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def default_db_path() -> str:
    return os.environ.get("ML_EXPERIMENT_TRACKER_DB", "experiments.db")


@dataclass(frozen=True)
class ExperimentRecord:
    id: str
    name: str
    description: str | None
    status: str
    notes: str | None
    created_at: str
    finished_at: str | None


class ExperimentStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or default_db_path()
        self._lock = threading.Lock()
        self._ensure_schema()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._lock, self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS experiment_tags (
                    experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                    tag TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, tag)
                );
                CREATE TABLE IF NOT EXISTS hyperparameters (
                    experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (experiment_id, key)
                );
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    step INTEGER,
                    logged_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_metrics_exp ON metrics(experiment_id);
                CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(experiment_id, name);
                """
            )

    def create_experiment(
        self,
        name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        hyperparameters: dict[str, Any] | None = None,
    ) -> str:
        exp_id = str(uuid.uuid4())
        created = _utc_now()
        tags = tags or []
        hyperparameters = hyperparameters or {}
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO experiments (id, name, description, status, notes, created_at, finished_at)
                VALUES (?, ?, ?, 'running', NULL, ?, NULL)
                """,
                (exp_id, name, description, created),
            )
            conn.executemany(
                "INSERT INTO experiment_tags (experiment_id, tag) VALUES (?, ?)",
                [(exp_id, t.strip()) for t in tags if t.strip()],
            )
            rows = [(exp_id, k, json.dumps(v)) for k, v in hyperparameters.items()]
            if rows:
                conn.executemany(
                    "INSERT INTO hyperparameters (experiment_id, key, value) VALUES (?, ?, ?)",
                    rows,
                )
        return exp_id

    def log_metric(self, experiment_id: str, name: str, value: float, step: int | None = None) -> None:
        with self._lock, self._connection() as conn:
            cur = conn.execute("SELECT 1 FROM experiments WHERE id = ?", (experiment_id,))
            if cur.fetchone() is None:
                raise ValueError(f"Unknown experiment_id: {experiment_id}")
            conn.execute(
                """
                INSERT INTO metrics (experiment_id, name, value, step, logged_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (experiment_id, name, value, step, _utc_now()),
            )

    def set_hyperparameter(self, experiment_id: str, key: str, value: Any) -> None:
        payload = json.dumps(value)
        with self._lock, self._connection() as conn:
            cur = conn.execute("SELECT 1 FROM experiments WHERE id = ?", (experiment_id,))
            if cur.fetchone() is None:
                raise ValueError(f"Unknown experiment_id: {experiment_id}")
            conn.execute(
                """
                INSERT INTO hyperparameters (experiment_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(experiment_id, key) DO UPDATE SET value = excluded.value
                """,
                (experiment_id, key, payload),
            )

    def add_tags(self, experiment_id: str, tags: list[str]) -> None:
        clean = [t.strip() for t in tags if t.strip()]
        if not clean:
            return
        with self._lock, self._connection() as conn:
            cur = conn.execute("SELECT 1 FROM experiments WHERE id = ?", (experiment_id,))
            if cur.fetchone() is None:
                raise ValueError(f"Unknown experiment_id: {experiment_id}")
            conn.executemany(
                """
                INSERT OR IGNORE INTO experiment_tags (experiment_id, tag) VALUES (?, ?)
                """,
                [(experiment_id, t) for t in clean],
            )

    def finish_experiment(
        self,
        experiment_id: str,
        status: str,
        notes: str | None = None,
    ) -> None:
        if status not in {"completed", "failed", "aborted"}:
            raise ValueError("status must be one of: completed, failed, aborted")
        finished = _utc_now()
        with self._lock, self._connection() as conn:
            cur = conn.execute(
                """
                UPDATE experiments
                SET status = ?, notes = COALESCE(?, notes), finished_at = ?
                WHERE id = ?
                """,
                (status, notes, finished, experiment_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Unknown experiment_id: {experiment_id}")

    def delete_experiment(self, experiment_id: str) -> bool:
        with self._lock, self._connection() as conn:
            cur = conn.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
            return cur.rowcount > 0

    def list_experiments(
        self,
        *,
        status: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> list[ExperimentRecord]:
        limit = max(1, min(limit, 500))
        query = """
            SELECT DISTINCT e.id, e.name, e.description, e.status, e.notes, e.created_at, e.finished_at
            FROM experiments e
        """
        args: list[Any] = []
        if tag:
            query += """
            INNER JOIN experiment_tags t ON t.experiment_id = e.id AND t.tag = ?
            """
            args.append(tag.strip())
        query += " WHERE 1=1 "
        if status:
            query += " AND e.status = ? "
            args.append(status)
        query += " ORDER BY e.created_at DESC LIMIT ? "
        args.append(limit)
        with self._lock, self._connection() as conn:
            rows = conn.execute(query, args).fetchall()
        return [
            ExperimentRecord(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                status=r["status"],
                notes=r["notes"],
                created_at=r["created_at"],
                finished_at=r["finished_at"],
            )
            for r in rows
        ]

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, name, description, status, notes, created_at, finished_at
                FROM experiments WHERE id = ?
                """,
                (experiment_id,),
            ).fetchone()
            if row is None:
                return None
            tags = [
                r[0]
                for r in conn.execute(
                    "SELECT tag FROM experiment_tags WHERE experiment_id = ? ORDER BY tag",
                    (experiment_id,),
                ).fetchall()
            ]
            hp_rows = conn.execute(
                "SELECT key, value FROM hyperparameters WHERE experiment_id = ? ORDER BY key",
                (experiment_id,),
            ).fetchall()
            hyperparameters = {r["key"]: json.loads(r["value"]) for r in hp_rows}
            metric_rows = conn.execute(
                """
                SELECT name, value, step, logged_at FROM metrics
                WHERE experiment_id = ?
                ORDER BY logged_at ASC, id ASC
                """,
                (experiment_id,),
            ).fetchall()
            metrics = [
                {
                    "name": r["name"],
                    "value": r["value"],
                    "step": r["step"],
                    "logged_at": r["logged_at"],
                }
                for r in metric_rows
            ]
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "status": row["status"],
            "notes": row["notes"],
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
            "tags": tags,
            "hyperparameters": hyperparameters,
            "metrics": metrics,
        }

    def compare_experiments(
        self,
        experiment_ids: list[str],
        metric_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if len(experiment_ids) < 2:
            raise ValueError("Provide at least two experiment_ids to compare.")
        out: list[dict[str, Any]] = []
        for eid in experiment_ids:
            detail = self.get_experiment(eid)
            if detail is None:
                raise ValueError(f"Unknown experiment_id: {eid}")
            metrics_summary: dict[str, Any] = {}
            by_name: dict[str, list[float]] = {}
            for m in detail["metrics"]:
                by_name.setdefault(m["name"], []).append(m["value"])
            names = metric_names if metric_names else sorted(by_name.keys())
            for name in names:
                vals = by_name.get(name)
                if not vals:
                    continue
                metrics_summary[name] = {"last": vals[-1], "min": min(vals), "max": max(vals), "count": len(vals)}
            out.append(
                {
                    "id": detail["id"],
                    "name": detail["name"],
                    "status": detail["status"],
                    "hyperparameters": detail["hyperparameters"],
                    "metrics_summary": metrics_summary,
                }
            )
        return out
