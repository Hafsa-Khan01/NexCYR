#!/bin/sh
# Container entrypoint: make /data writable, then drop privileges.
#
# Platform-mounted volumes (Railway, ECS, host bind-mounts) are frequently owned
# by root, which a non-root container cannot write to. Starting as root, fixing
# ownership and then dropping to the unprivileged `nexcyr` user handles every
# case, including a volume that was created empty by the orchestrator.
set -e

DATA_DIR="${REPORTS_DIR:-/data/reports}"
DATA_ROOT="${DATA_DIR%/reports}"

mkdir -p "$DATA_DIR" 2>/dev/null || true

if [ "$(id -u)" = "0" ]; then
    chown -R nexcyr:nexcyr "$DATA_ROOT" 2>/dev/null || true

    if command -v setpriv >/dev/null 2>&1; then
        exec setpriv --reuid=nexcyr --regid=nexcyr --init-groups "$@"
    fi

    # No setpriv in this base image: keep running rather than fail the deploy.
    echo "[nexcyr] setpriv unavailable; continuing as root." >&2
fi

exec "$@"
