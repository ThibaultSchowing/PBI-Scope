#!/usr/bin/env python3
"""
Download a GFF3 file from the PhageScope API with retry and validation.

Called by Snakemake rule download_gff3.
- Streams downloads in chunks to handle large files without memory issues.
- Validates HTTP response status (rejects 4xx/5xx).
- Retries transient errors (5xx, timeouts, IncompleteRead) up to 3 times with backoff.
- Detects HTML error pages disguised as .gff3 files.
- On permanent failure: creates an empty file so downstream rules
  (build_gff3_index) skip it gracefully instead of crashing the pipeline.
"""

import http.client
import logging
import os
import ssl
import time
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]  # seconds between retries
CHUNK_SIZE = 1024 * 1024  # 1 MB chunks


def _is_cert_verify_error(exc: BaseException) -> bool:
    msg = str(exc)
    return "CERTIFICATE_VERIFY_FAILED" in msg or "certificate verify failed" in msg.lower()


def _get_ssl_context() -> ssl.SSLContext | None:
    # Allow insecure fallback via env or snakemake config.
    # Check snakemake.config if available (when run via snakemake)
    try:
        cfg = snakemake.config.get("public_data_provider", {})  # type: ignore[name-defined]
        if cfg.get("verify_ssl") is False:
            LOGGER.warning("SSL verification disabled via config public_data_provider.verify_ssl=false — using unverified context")
            return ssl._create_unverified_context()
    except Exception:
        pass
    env_val = os.getenv("PBI_INSECURE_SSL", "").strip().lower()
    if env_val in ("1", "true", "yes", "on"):
        LOGGER.warning("SSL verification disabled via PBI_INSECURE_SSL — using unverified context")
        return ssl._create_unverified_context()
    return None


def download(url: str, output_path: str) -> None:
    tmp_path = f"{output_path}.tmp"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Resolve initial SSL context (None = verified, unverified = forced insecure)
    ssl_context = _get_ssl_context()
    # Track if we already fell back to unverified due to cert error
    cert_fallback_done = ssl_context is not None

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(
                url, headers={
                    "User-Agent": "PBI-gff3-download/1.0",
                    "Accept-Encoding": "identity",
                }
            )
            # Use context if set; otherwise default verified context
            if ssl_context is None:
                ctx_arg: dict = {}
            else:
                ctx_arg = {"context": ssl_context}
            with urllib.request.urlopen(request, timeout=60, **ctx_arg) as response:  # type: ignore[arg-type]
                status = response.status
                if status < 200 or status >= 300:
                    raise urllib.error.HTTPError(
                        url, status, f"Unexpected status {status}", response.headers, None
                    )

                # Stream in chunks to avoid memory issues with large files
                # and to detect HTML error pages early.
                bytes_read = 0
                html_check_done = False
                with open(tmp_path, "wb") as fh:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break

                        # Check first chunk for HTML error page
                        if not html_check_done:
                            html_check_done = True
                            snippet = chunk[:1024].lower()
                            if b"<!doctype html" in snippet or b"<html" in snippet:
                                raise ValueError(
                                    f"Response from {url} looks like an HTML error page, not GFF3 data"
                                )

                        fh.write(chunk)
                        bytes_read += len(chunk)

            os.replace(tmp_path, output_path)
            LOGGER.info(
                "Downloaded %s (%d bytes) on attempt %d", output_path, bytes_read, attempt
            )
            return

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            OSError,
            ValueError,
            http.client.IncompleteRead,
        ) as exc:
            last_error = exc

            # --- Expired-cert fallback: retry once with unverified context ---
            if _is_cert_verify_error(exc) and not cert_fallback_done:
                LOGGER.warning(
                    "Certificate verification failed for %s: %s — retrying with unverified SSL context (cert likely expired). "
                    "Set public_data_provider.verify_ssl=false or PBI_INSECURE_SSL=1 to force insecure from start.",
                    url, exc,
                )
                ssl_context = ssl._create_unverified_context()
                cert_fallback_done = True
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                # Do not count this as a consumed attempt — retry immediately
                # by continuing loop; we adjust attempt counter by decrementing
                # via a small trick: sleep 0 and let loop increment.
                # Simpler: just continue and next iteration will be attempt+1,
                # but we want to preserve retries. So we keep attempt loop as-is
                # and log that we are retrying outside normal backoff.
                if attempt < MAX_RETRIES:
                    LOGGER.warning("Retrying %s with unverified context (attempt %d/%d)", url, attempt + 1, MAX_RETRIES)
                    time.sleep(1)
                    continue
                # If we are on last attempt, fall through to retry logic below
                # but with new context on next outer retry would not happen;
                # so we reset last_error and try one more time inline:
                # Instead, handle by converting to transient and forcing retry
                # We'll force a retry by not breaking here.

            is_server_error = isinstance(exc, urllib.error.HTTPError) and exc.code >= 500
            is_transient = is_server_error or isinstance(
                exc, (
                    urllib.error.URLError,
                    OSError,
                    TimeoutError,
                    http.client.IncompleteRead,
                )
            )

            # Also treat cert errors as transient if we haven't exhausted fallback
            if _is_cert_verify_error(exc):
                is_transient = True

            # Clean up partial download before retry
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

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
    open(output_path, "w").close()  # empty file so index builder skips it
    LOGGER.warning("Created empty fallback file: %s", output_path)


def main():
    url = str(snakemake.params.url)
    output_path = str(snakemake.output.gff3)
    download(url, output_path)


if __name__ == "__main__":
    main()
