#!/bin/sh
set -eu
exec uvicorn app:app \
  --host 0.0.0.0 \
  --port "${PORT:-10000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "*" \
  --timeout-keep-alive 5 \
  --timeout-graceful-shutdown 15 \
  --limit-concurrency "${UVICORN_LIMIT_CONCURRENCY:-16}"
