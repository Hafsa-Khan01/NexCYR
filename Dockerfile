# NexCYR — single-container deployment image.
# Works unchanged on Railway, Fly.io, Render, Docker Compose and a plain VPS.
#
# SECURITY NOTE: nmap is deliberately NOT installed in this image. Running port
# scans from a shared cloud host can breach provider ToS and, worse, touch
# networks you are not authorized to scan. The NexCYR Cloud therefore reports
# NMAP_UNAVAILABLE for its own scanner and routes real scans to an enrolled
# Agent that sits inside an explicitly authorized target network.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Dependencies first so the layer is cached across code-only changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite database and generated PDF reports must survive redeploys, so they live
# on a mounted volume rather than inside the ephemeral container filesystem.
# These are the only paths the app writes to; /app itself stays read-only.
RUN useradd --create-home --shell /usr/sbin/nologin nexcyr \
    && mkdir -p /data/reports \
    && chmod +x /app/deploy/docker-entrypoint.sh \
    && chown -R nexcyr:nexcyr /app /data

ENV DATABASE_URL=sqlite:////data/nexcyr.db \
    REPORTS_DIR=/data/reports

VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

# No USER directive on purpose: the entrypoint starts as root only to chown the
# platform-mounted volume (usually root-owned), then drops to `nexcyr`.
ENTRYPOINT ["/app/deploy/docker-entrypoint.sh"]

# Single worker: SQLite serializes writes, and multiple workers would contend on
# the same database file. Scale by moving to Postgres via DATABASE_URL instead.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
