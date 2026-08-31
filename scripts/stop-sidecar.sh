#!/usr/bin/env bash
# 停止后台 sidecar。
set -e
if [ -f /tmp/nextchapter-sidecar.pid ]; then
  PID=$(cat /tmp/nextchapter-sidecar.pid)
  if kill -0 "$PID" 2>/dev/null; then
    echo "==> 停止 sidecar (pid=$PID)..."
    kill "$PID"
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" || true
    fi
  fi
  rm -f /tmp/nextchapter-sidecar.pid
  echo "==> ✅ stopped"
else
  echo "==> 没有后台 sidecar 在跑"
fi
