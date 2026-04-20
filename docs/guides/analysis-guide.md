# Analysis Container Guide

The analysis container is the recommended way to consume PBI data.

## Access options

### Preferred: VS Code Dev Containers

Use **VS Code Remote – Containers / Dev Containers** to attach to the `analysis` service.
This is the preferred workflow because it provides a full IDE (editor, terminal, debugger, extensions).

### Stable fallback: Jupyter Lab

Start and open:

```bash
docker compose up -d analysis
```

If remote, tunnel first:

```bash
ssh -L 8888:localhost:8888 user@server
```

Open `http://localhost:8888`.

Jupyter Lab is stable, but not the preferred option when a full IDE workflow is needed.

## OOM warning

Large joins and sequence materialization can trigger out-of-memory errors.
Use filtering, limits, and batch/iterator patterns.

## Quick Python start

```python
from pbi import quick_connect

retriever = quick_connect()
stats = retriever.get_stats()
print(stats['database'])
```

## Recommended notebooks

- `01_database_exploration.ipynb`
- `02_sequence_retrieval.ipynb`
- `03_ml_streaming.ipynb`
- `00_pipeline_logs.ipynb`
