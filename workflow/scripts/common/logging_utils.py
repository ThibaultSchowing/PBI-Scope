#!/usr/bin/env python3
"""
Shared logging setup utilities for Snakemake-executed Python scripts.

Usage in a Snakemake script::

    from common.logging_utils import setup_logging
    setup_logging(snakemake.log[0])
    logging.info("Starting step …")

Or when the script directory is on sys.path directly::

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common'))
    from logging_utils import setup_logging
"""

import logging
import sys
from pathlib import Path


def setup_logging(
    log_file: str,
    level: int = logging.INFO,
    also_stderr: bool = True,
) -> None:
    """Configure the root logger to write to *log_file*.

    Args:
        log_file:    Path to the log file (usually ``snakemake.log[0]``).
                     Parent directories are created automatically.
        level:       Logging level for both handlers (default: INFO).
        also_stderr: When *True* (default) also attach a StreamHandler to
                     stderr so progress is visible on the console / in
                     Snakemake's live output.

    The function clears any handlers that were previously attached to the
    root logger to avoid duplicate lines when the module is imported multiple
    times (e.g. in test environments).
    """
    # Ensure parent directories exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    # File handler — the primary target for Snakemake log: files
    fh = logging.FileHandler(str(log_path))
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Optional stderr handler — keeps live console visibility
    if also_stderr:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)
