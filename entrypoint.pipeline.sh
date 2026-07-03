#!/bin/sh
# Dynamic entrypoint for the pipeline container.
#
# Problem: Docker allows running a container as an arbitrary host UID/GID via
# "user: UID:GID" in docker-compose.yml.  That UID typically has no entry in
# the container's /etc/passwd.  Python's getpass.getuser() (called internally
# by Snakemake) does:
#
#   import pwd, os
#   pwd.getpwuid(os.getuid())   # raises KeyError if UID not in /etc/passwd
#
# The KeyError propagates as an unhandled exception that kills the process.
#
# Fix: write a minimal /etc/passwd entry for the current UID at container
# start-up time (before exec-ing the main process).  This is the same
# technique used by Red Hat UBI / OpenShift compatible images.

CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

# Ensure getpass.getuser() has environment fallbacks when /etc/passwd cannot be modified.
export USER="${USER:-pipeline}"
export LOGNAME="${LOGNAME:-${USER}}"

# Only patch if the UID is absent and /etc/passwd is writable, so we avoid
# both unnecessary writes and noisy permission errors when /etc/passwd is
# read-only at runtime.
if ! getent passwd "${CURRENT_UID}" > /dev/null 2>&1 && [ -w /etc/passwd ]; then
    # /etc/passwd may be read-only in some hardened setups; tolerate failure.
    echo "pipeline:x:${CURRENT_UID}:${CURRENT_GID}:Pipeline user:/cache:/bin/sh" \
        >> /etc/passwd 2>/dev/null || true
fi

exec "$@"
