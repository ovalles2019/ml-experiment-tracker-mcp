"""MCP server: tools and resources for ML experiment tracking."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ml_experiment_tracker_mcp.store import ExperimentStore, default_db_path

mcp = FastMCP(
    "ML Experiment Tracker",
    instructions=(
        "Track machine learning experiments: create runs, log metrics and hyperparameters, "
        "finish runs, list and compare experiments. Data is stored in SQLite "
        f"(default file: {default_db_path()} — override with ML_EXPERIMENT_TRACKER_DB)."
    ),
)

_store = ExperimentStore()


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def create_experiment(
    name: str,
    description: str | None = None,
    tags: list[str] | None = None,
    hyperparameters: dict[str, Any] | None = None,
) -> str:
    """Start a new experiment run. Returns the new experiment_id (UUID)."""
    exp_id = _store.create_experiment(
        name=name,
        description=description,
        tags=tags,
        hyperparameters=hyperparameters,
    )
    return _json({"experiment_id": exp_id, "status": "running"})


@mcp.tool()
def log_metric(
    experiment_id: str,
    metric_name: str,
    value: float,
    step: int | None = None,
) -> str:
    """Append a scalar metric for an experiment (e.g. loss, accuracy)."""
    try:
        _store.log_metric(experiment_id, metric_name, value, step)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)})
    return _json({"ok": True, "experiment_id": experiment_id, "metric": metric_name, "value": value, "step": step})


@mcp.tool()
def set_hyperparameter(experiment_id: str, key: str, value: Any) -> str:
    """Set or update a single hyperparameter (value may be string, number, bool, or nested JSON)."""
    try:
        _store.set_hyperparameter(experiment_id, key, value)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)})
    return _json({"ok": True, "experiment_id": experiment_id, "key": key})


@mcp.tool()
def add_experiment_tags(experiment_id: str, tags: list[str]) -> str:
    """Attach tags to an experiment (e.g. model=gpt, dataset=cifar10)."""
    try:
        _store.add_tags(experiment_id, tags)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)})
    return _json({"ok": True, "experiment_id": experiment_id, "tags": tags})


@mcp.tool()
def finish_experiment(
    experiment_id: str,
    status: str,
    notes: str | None = None,
) -> str:
    """Mark an experiment completed, failed, or aborted. Status: completed | failed | aborted."""
    try:
        _store.finish_experiment(experiment_id, status, notes)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)})
    return _json({"ok": True, "experiment_id": experiment_id, "status": status})


@mcp.tool()
def list_experiments(
    status: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> str:
    """List recent experiments with optional filters (status, tag)."""
    rows = _store.list_experiments(status=status, tag=tag, limit=limit)
    return _json(
        [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "status": r.status,
                "created_at": r.created_at,
                "finished_at": r.finished_at,
            }
            for r in rows
        ]
    )


@mcp.tool()
def get_experiment_detail(experiment_id: str) -> str:
    """Return full detail for one experiment: tags, hyperparameters, and all logged metrics."""
    detail = _store.get_experiment(experiment_id)
    if detail is None:
        return _json({"error": f"Unknown experiment_id: {experiment_id}"})
    return _json(detail)


@mcp.tool()
def compare_experiments(experiment_ids: list[str], metric_names: list[str] | None = None) -> str:
    """Compare two or more experiments: hyperparameters and metric aggregates (last, min, max)."""
    try:
        data = _store.compare_experiments(experiment_ids, metric_names)
    except ValueError as e:
        return _json({"error": str(e)})
    return _json(data)


@mcp.tool()
def delete_experiment(experiment_id: str) -> str:
    """Permanently delete an experiment and its metrics."""
    deleted = _store.delete_experiment(experiment_id)
    return _json({"deleted": deleted, "experiment_id": experiment_id})


@mcp.resource("experiment://{experiment_id}")
def experiment_resource(experiment_id: str) -> str:
    """Load one experiment into context as JSON text."""
    detail = _store.get_experiment(experiment_id)
    if detail is None:
        return _json({"error": f"Unknown experiment_id: {experiment_id}"})
    return _json(detail)


@mcp.prompt()
def compare_runs_prompt(experiment_id_a: str, experiment_id_b: str) -> str:
    """Template for asking an assistant to compare two experiment runs."""
    return (
        "You have access to the ML Experiment Tracker tools. "
        f"Fetch details for experiments {experiment_id_a} and {experiment_id_b}, "
        "then explain which run performed better and why, based on metrics and hyperparameters. "
        "Call compare_experiments if a side-by-side summary helps."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
