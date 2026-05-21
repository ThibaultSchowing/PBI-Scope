"""
Shared utilities for PBI Jupyter notebooks.

Import in any notebook with:
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path.cwd().parent / '_shared'))
    from notebook_utils import print_env_info, get_results_dir

Or, from a notebook in the notebooks/ directory:
    import sys; sys.path.insert(0, '_shared')
    from notebook_utils import print_env_info, get_results_dir
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def print_env_info(notebook_name: str = "") -> None:
    """Print a short environment summary at notebook startup.

    Displays the PBI package version, Python version, and whether the
    notebook is running inside the Docker analysis container.
    """
    try:
        # Add src to path if running from notebooks/ directory
        project_root = Path.cwd().parent
        src_path = str(project_root / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        import pbi
        pbi_version = getattr(pbi, "__version__", "unknown")
    except ImportError:
        pbi_version = "not installed"

    in_docker = bool(os.environ.get("DATA_PATH"))
    env_label = "Docker container" if in_docker else "local / dev"

    header = f"  {notebook_name}  " if notebook_name else "  PBI notebook  "
    print("=" * (len(header) + 4))
    print(f"  {header.strip()}")
    print("=" * (len(header) + 4))
    print(f"  pbi version : {pbi_version}")
    print(f"  Python      : {sys.version.split()[0]}")
    print(f"  Environment : {env_label}")
    print()


def get_results_dir(notebook_name: str) -> Path:
    """Return (and create) the notebook's durable results directory.

    The root is controlled by the ``PBI_RESULTS_DIR`` environment variable
    (default ``/results`` in Docker, ``./outputs`` locally).

    Parameters
    ----------
    notebook_name:
        Sub-directory name, typically the notebook filename stem,
        e.g. ``"05_end_to_end_walkthrough"``.

    Returns
    -------
    Path
        ``<results_root>/<notebook_name>/`` — always exists on return.
    """
    results_root = Path(os.getenv("PBI_RESULTS_DIR", "/results"))
    if not results_root.exists():
        # Fall back to local outputs/ directory
        project_root = Path.cwd().parent
        local_out = project_root / "outputs"
        if local_out.exists():
            results_root = local_out

    nb_dir = results_root / notebook_name
    nb_dir.mkdir(parents=True, exist_ok=True)
    return nb_dir


def read_provenance_json(logs_root: Path | None = None) -> dict:
    """Read the pipeline run provenance JSON artifact if available.

    Parameters
    ----------
    logs_root:
        Root of the pipeline-logs directory.  Defaults to ``/pipeline-logs``.

    Returns
    -------
    dict
        Provenance fields, or an empty dict if the file does not exist.
    """
    import json

    if logs_root is None:
        logs_root = Path("/pipeline-logs")
    prov_path = logs_root / "csv" / "pipeline_run_provenance.json"
    if prov_path.exists():
        with prov_path.open() as fh:
            return json.load(fh)
    return {}


def print_provenance(logs_root: Path | None = None) -> None:
    """Print pipeline run provenance fields to stdout."""
    prov = read_provenance_json(logs_root)
    if not prov:
        print("ℹ️  No pipeline_run_provenance.json found — pipeline may not have run yet.")
        return
    print("Pipeline run provenance:")
    for key, value in prov.items():
        print(f"  {key:<36} {value}")
