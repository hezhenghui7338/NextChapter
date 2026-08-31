#!/usr/bin/env bash
# 后台启动 sidecar，日志写到 /tmp/nextchapter-sidecar.log，PID 写到 /tmp/nextchapter-sidecar.pid。
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 清理旧 PID
if [ -f /tmp/nextchapter-sidecar.pid ]; then
  OLD_PID=$(cat /tmp/nextchapter-sidecar.pid)
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "==> 停止旧 sidecar (pid=$OLD_PID)..."
    kill "$OLD_PID" || true
    sleep 1
  fi
  rm -f /tmp/nextchapter-sidecar.pid
fi

if [ -z "$NC_LLM_API_KEY" ]; then
  echo "⚠️  NC_LLM_API_KEY 未设置。请先 export NC_LLM_API_KEY=..."
  exit 1
fi

if [ -d ".venv" ]; then
  PYTHON=".venv/bin/python3"
else
  PYTHON="python3"
fi

echo "==> 启动 sidecar（后台）..."
nohup "$PYTHON" -m nextchapter_core.api.server > /tmp/nextchapter-sidecar.log 2>&1 &
echo $! > /tmp/nextchapter-sidecar.pid
PID=$(cat /tmp/nextchapter-sidecar.pid)
echo "==> sidecar PID: $PID"
echo "==> 日志: tail -f /tmp/nextchapter-sidecar.log"

# 等待 health
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://127.0.0.1:18432/health >/dev/null 2>&1; then
    echo "==> ✅ sidecar 已在 http://127.0.0.1:18432 就绪"
    exit 0
  fi
  sleep 0.5
done

echo "❌ sidecar 启动失败（10 秒内未响应）。查看日志："
tail -20 /tmp/nextchapter-sidecar.log
exit 1
