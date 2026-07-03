#!/usr/bin/env python3
"""
Download a .tar.gz archive from the PhageScope API with retry and validation.

Called by Snakemake rules download_protein_fasta and download_phage_fasta.
- Validates HTTP response status (rejects 4xx/5xx).
- Retries transient errors (5xx, timeouts) up to 3 times with backoff.
- Detects HTML error pages disguised as .tar.gz files.
- On permanent failure: creates a valid empty .tar.gz so downstream
  extract rules skip extraction gracefully instead of crashing the pipeline.
"""

import logging
import os
import subprocess
import time
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]  # seconds between retries
TIMEOUT = 300  # seconds per request (tar.gz files can be large)


def _is_html_content(data: bytes) -> bool:
    """Heuristic: check if the downloaded bytes look like an HTML error page."""
    snippet = data[:1024].lower()
    return b"<!doctype html" in snippet or b"<html" in snippet


def _create_empty_tar_gz(output_path: str) -> None:
    """Create a valid empty .tar.gz file so downstream tar -xzf doesn't crash."""
    subprocess.run(
        ["tar", "-czf", output_path, "--files-from", "/dev/null"],
        check=True,
        capture_output=True,
    )


def download(url: str, output_path: str) -> None:
    tmp_path = f"{output_path}.tmp"

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "PBI-archive-download/1.0"}
            )
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                status = response.status
                if status < 200 or status >= 300:
                    raise urllib.error.HTTPError(
                        url, status, f"Unexpected status {status}", response.headers, None
                    )
                body = response.read()

            if _is_html_content(body):
                raise ValueError(
                    f"Response from {url} looks like an HTML error page, not a tar.gz archive"
                )

            with open(tmp_path, "wb") as fh:
                fh.write(body)
            os.replace(tmp_path, output_path)
            LOGGER.info(
                "Downloaded %s (%d bytes) on attempt %d", output_path, len(body), attempt
            )
            return

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            OSError,
            ValueError,
        ) as exc:
            last_error = exc
            is_server_error = isinstance(exc, urllib.error.HTTPError) and exc.code >= 500
            is_transient = is_server_error or isinstance(
                exc, (urllib.error.URLError, OSError, TimeoutError)
            )

            if attempt < MAX_RETRIES and is_transient:
                wait = RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)]
                LOGGER.warning(
                    "Attempt %d/%d failed for %s: %s — retrying in %ds",
                    attempt,
                    MAX_RETRIES,
                    url,
                    exc,
                    wait,
                )
                time.sleep(wait)
            else:
                break

    # All retries exhausted or permanent failure
    LOGGER.error("Failed to download %s after %d attempts: %s", url, attempt, last_error)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    _create_empty_tar_gz(output_path)
    LOGGER.warning("Created empty fallback archive: %s", output_path)


def main():
    url = str(snakemake.params.url)
    output_path = str(snakemake.output.archive)
    download(url, output_path)


if __name__ == "__main__":
    main()
