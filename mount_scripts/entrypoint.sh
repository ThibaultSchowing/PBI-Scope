#!/bin/bash
# =============================================================================
# Entrypoint Script for Custom PBI-Scope Container
# =============================================================================
# This script handles:
#   1. /etc/passwd patching for arbitrary UID support (Docker best practice)
#   2. Switching between Jupyter Lab and script execution modes
#
# Usage:
#   ./entrypoint.sh jupyter    → Start Jupyter Lab (default)
#   ./entrypoint.sh script     → Run explore_phages.R
#   ./entrypoint.sh bash       → Open a shell (for debugging)
#
# The MODE is passed as the first argument to the entrypoint.
# In docker-compose.yml, this is set via the "command:" key.
# =============================================================================

# --- /etc/passwd Patching -----------------------------------------------------
# When running as a non-root user (via docker-compose user:), the container
# may not have an entry in /etc/passwd. This causes Python's getpass.getuser()
# to fail with a KeyError. This patch adds a temporary entry.
#
# This is a standard pattern used by Red Hat UBI and OpenShift containers.
CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)
export USER="${USER:-jupyter}"
export LOGNAME="${LOGNAME:-${USER}}"

if ! getent passwd "${CURRENT_UID}" > /dev/null 2>&1 && [ -w /etc/passwd ]; then
    echo "jupyter:x:${CURRENT_UID}:${CURRENT_GID}:Jupyter user:${HOME:-/workspace}:/bin/sh" \
        >> /etc/passwd 2>/dev/null || true
fi

# --- Mode Selection -----------------------------------------------------------
# The MODE variable determines what the container does.
# It defaults to "jupyter" if not specified.
MODE="${1:-jupyter}"

case "${MODE}" in
    jupyter)
        # -----------------------------------------------------------------
        # Jupyter Lab Mode
        # -----------------------------------------------------------------
        # Starts Jupyter Lab with:
        #   - No authentication (safe for localhost/SSH tunnel only)
        #   - XSRF protection disabled (required for localhost access)
        #   - Notebook directory set to /workspace (the bind mount)
        #
        # Security note: This configuration is safe for:
        #   - Localhost only (port not exposed)
        #   - SSH tunnel from your laptop to the server
        #
        # It is NOT safe for:
        #   - Server port 8888 open to the internet
        #   - Server on a shared/untrusted LAN
        #
        # To add authentication, set JUPYTER_TOKEN environment variable.
        echo "=== Starting Jupyter Lab ==="
        echo "=== Open http://localhost:8888 in your browser ==="
        exec jupyter lab \
            --ip=0.0.0.0 \
            --port=8888 \
            --no-browser \
            --notebook-dir=/workspace \
            --ServerApp.disable_check_xsrf=True \
            --ServerApp.token=
        ;;

    script)
        # -----------------------------------------------------------------
        # Script Mode
        # -----------------------------------------------------------------
        # Runs the R exploration script and exits.
        # Plots are saved to /workspace/output/ (bind-mounted to ./output/).
        #
        # To run a different script, modify this section or pass a different
        # command via docker-compose or docker run.
        #
        # For long-running scripts, consider:
        #   - Adding logging to a file: Rscript my_script.R 2>&1 | tee output/log.txt
        #   - Using nohup for background execution
        #   - Adding a health check to monitor progress
        echo "=== Running R Exploration Script ==="
        cd /workspace
        Rscript explore_phages.R
        echo "=== Done! Plots saved to /workspace/output/ ==="
        ;;

    bash)
        # -----------------------------------------------------------------
        # Bash Mode (for debugging)
        # -----------------------------------------------------------------
        # Opens a shell so you can explore the container, test commands,
        # or debug issues interactively.
        #
        # Usage:
        #   docker compose -f docker-compose.custom.yml run custom-jupyter bash
        echo "=== Opening Shell ==="
        exec /bin/bash
        ;;

    *)
        # -----------------------------------------------------------------
        # Unknown Mode
        # -----------------------------------------------------------------
        echo "Unknown mode: ${MODE}"
        echo "Usage: ./entrypoint.sh [jupyter|script|bash]"
        exit 1
        ;;
esac
