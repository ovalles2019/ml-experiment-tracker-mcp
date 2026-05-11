# ML Experiment Tracker MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that lets assistants **create experiment runs**, **log metrics**, **record hyperparameters**, **tag runs**, and **compare results**. Persistence is **SQLite**, so your history survives across sessions.

## Stack

- Python 3.10+
- Official MCP Python SDK (`mcp`) with **FastMCP**
- **SQLite** for experiments, tags, hyperparameters, and time-series metrics

## Quick start

```bash
cd "/path/to/ml-experiment-tracker-mcp"
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Run the server (stdio — used by Cursor and similar clients):

```bash
python -m ml_experiment_tracker_mcp.server
```

Or:

```bash
ml-experiment-tracker-mcp
```

Dev / inspector (requires MCP CLI extras):

```bash
pip install "mcp[cli]"
mcp dev ml_experiment_tracker_mcp/server.py
```

## Cursor setup

In **Cursor Settings → MCP**, add a server:

```json
{
  "mcpServers": {
    "ml-experiment-tracker": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "ml_experiment_tracker_mcp.server"],
      "cwd": "/absolute/path/to/ml-experiment-tracker-mcp"
    }
  }
}
```

Optional: set `ML_EXPERIMENT_TRACKER_DB` to a full path for the SQLite file (default: `experiments.db` in the process working directory).

## Tools

| Tool | Purpose |
|------|--------|
| `create_experiment` | New run with optional description, tags, hyperparameters |
| `log_metric` | Log a scalar (e.g. loss / accuracy), optional step |
| `set_hyperparameter` | Update one hyperparameter |
| `add_experiment_tags` | Add tags |
| `finish_experiment` | Mark `completed`, `failed`, or `aborted` |
| `list_experiments` | Filter by status/tag |
| `get_experiment_detail` | Full run with all metrics |
| `compare_experiments` | Side-by-side metric aggregates |
| `delete_experiment` | Remove a run |

**Resource:** `experiment://{experiment_id}` — same payload as `get_experiment_detail`.

## Resume angle

You can describe this project as: *Designed and shipped an MCP server for ML experiment tracking with SQLite persistence, exposing typed tools/resources for LLM clients (Cursor, Claude, etc.).*

## License

MIT
