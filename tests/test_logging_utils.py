#!/usr/bin/env python3
"""
Unit tests for workflow/scripts/common/logging_utils.py

Verifies that ``setup_logging``:
- creates parent log directories automatically
- writes log output to the specified file
- optionally attaches a stderr handler
- does not duplicate handlers on repeated calls
"""

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add the common scripts directory to sys.path
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "workflow" / "scripts" / "common"),
)

from logging_utils import setup_logging


class TestSetupLogging(unittest.TestCase):
    """Tests for setup_logging()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Reset root logger state between tests
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def tearDown(self):
        import shutil
        # Close all file handlers before cleanup to avoid Windows locking issues
        root = logging.getLogger()
        for h in list(root.handlers):
            h.close()
            root.removeHandler(h)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Directory creation
    # ------------------------------------------------------------------

    def test_creates_parent_directories(self):
        """setup_logging creates nested parent directories if needed."""
        log_file = os.path.join(self.tmpdir, "sub", "dir", "pipeline.log")
        setup_logging(log_file, also_stderr=False)
        self.assertTrue(Path(log_file).parent.exists())

    # ------------------------------------------------------------------
    # File output
    # ------------------------------------------------------------------

    def test_log_message_written_to_file(self):
        """A log.info message is written to the specified log file."""
        log_file = os.path.join(self.tmpdir, "test.log")
        setup_logging(log_file, also_stderr=False)

        logging.info("hello from test")
        # Flush file handler
        for h in logging.getLogger().handlers:
            h.flush()

        content = Path(log_file).read_text()
        self.assertIn("hello from test", content)

    def test_log_file_is_created(self):
        """The log file is created on first write."""
        log_file = os.path.join(self.tmpdir, "created.log")
        setup_logging(log_file, also_stderr=False)
        logging.info("create it")
        for h in logging.getLogger().handlers:
            h.flush()
        self.assertTrue(Path(log_file).exists())

    # ------------------------------------------------------------------
    # Handler counts
    # ------------------------------------------------------------------

    def test_no_duplicate_handlers_on_repeated_call(self):
        """Calling setup_logging twice does not add duplicate handlers."""
        log_file = os.path.join(self.tmpdir, "dup.log")
        setup_logging(log_file, also_stderr=False)
        setup_logging(log_file, also_stderr=False)
        self.assertEqual(len(logging.getLogger().handlers), 1)

    def test_stderr_handler_added_when_requested(self):
        """A StreamHandler to stderr is present when also_stderr=True."""
        log_file = os.path.join(self.tmpdir, "stderr.log")
        setup_logging(log_file, also_stderr=True)
        handlers = logging.getLogger().handlers
        stderr_handlers = [
            h for h in handlers if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        self.assertEqual(len(stderr_handlers), 1)

    def test_no_stderr_handler_when_not_requested(self):
        """No StreamHandler is attached when also_stderr=False."""
        log_file = os.path.join(self.tmpdir, "no_stderr.log")
        setup_logging(log_file, also_stderr=False)
        handlers = logging.getLogger().handlers
        non_file_stream = [
            h for h in handlers if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        self.assertEqual(len(non_file_stream), 0)

    # ------------------------------------------------------------------
    # Log level
    # ------------------------------------------------------------------

    def test_default_level_is_info(self):
        """Root logger level defaults to INFO."""
        log_file = os.path.join(self.tmpdir, "level.log")
        setup_logging(log_file, also_stderr=False)
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_custom_level_respected(self):
        """Custom level is applied to the root logger."""
        log_file = os.path.join(self.tmpdir, "debug.log")
        setup_logging(log_file, level=logging.DEBUG, also_stderr=False)
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    # ------------------------------------------------------------------
    # Format
    # ------------------------------------------------------------------

    def test_log_format_contains_timestamp(self):
        """Log messages include a timestamp in the standard format."""
        log_file = os.path.join(self.tmpdir, "fmt.log")
        setup_logging(log_file, also_stderr=False)
        logging.info("format check")
        for h in logging.getLogger().handlers:
            h.flush()
        content = Path(log_file).read_text()
        # Timestamp format: YYYY-MM-DD HH:MM:SS,mmm
        import re
        self.assertRegex(content, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
