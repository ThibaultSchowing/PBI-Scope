#!/bin/bash
# Dynamic entrypoint for the analysis container.
#
# 1. Patches /etc/passwd so that Python's getpass.getuser() works when the
#    container runs as an arbitrary host UID/GID (Red Hat UBI / OpenShift pattern).
#
# 2. Builds the Jupyter Lab command with optional token authentication:
#    - JUPYTER_TOKEN env var not set / empty: no authentication (default)
#    - JUPYTER_TOKEN env var set: token-based auth required
#
# The image CMD ("jupyter lab ...") arrives as positional arguments on every
# `docker compose up`. It is NOT executed as-is: the entrypoint owns the final
# command so that auth flags can be injected. Any other explicit command
# (e.g. `docker compose run --rm analysis bash`) is executed directly.

# ---------------------------------------------------------------------------
# /etc/passwd patching for arbitrary UID support
# ---------------------------------------------------------------------------
CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

export USER="${USER:-jupyter}"
export LOGNAME="${LOGNAME:-${USER}}"

if ! getent passwd "${CURRENT_UID}" > /dev/null 2>&1 && [ -w /etc/passwd ]; then
    echo "jupyter:x:${CURRENT_UID}:${CURRENT_GID}:Jupyter user:${HOME:-/workspace}:/bin/sh" \
        >> /etc/passwd 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Jupyter Lab command construction
# ---------------------------------------------------------------------------
CMD_ARGS=(
    "--ip=0.0.0.0"
    "--port=8888"
    "--no-browser"
    "--notebook-dir=/workspace"
    "--ServerApp.disable_check_xsrf=True"
)

if [ -n "${JUPYTER_TOKEN}" ]; then
    CMD_ARGS+=("--IdentityProvider.token=${JUPYTER_TOKEN}")
    echo "=== Jupyter Lab: token authentication enabled ==="
    echo "=== Open http://localhost:8888/lab?token=${JUPYTER_TOKEN} ==="
else
    CMD_ARGS+=("--IdentityProvider.token=")
    CMD_ARGS+=("--IdentityProvider.password=")
    CMD_ARGS+=("--ServerApp.allow_remote_access=True")
    echo "=== Jupyter Lab: running without authentication ==="
fi

# The image CMD starts with "jupyter" and must be replaced by the flagged
# command above — otherwise Jupyter would run WITHOUT auth flags and generate
# a random token. Any other explicit command (bash, python, ...) runs as-is.
if [ $# -gt 0 ] && [ "$1" != "jupyter" ]; then
    exec "$@"
fi
exec jupyter lab "${CMD_ARGS[@]}"
