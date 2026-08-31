#!/usr/bin/env bash
# 端到端联通测试：sidecar 起来后跑 /health + /ingest/paste，验证基本链路。
# 不需要真实 API key（用 mock LLM 配置）。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> 启动 sidecar (test-mode, mock LLM)..."
cd "$ROOT/packages/nextchapter-core"
source .venv/bin/activate 2>/dev/null || true

# 用一个无效 API key + 快速超时，纯测启动和 ingest 流程
NC_LLM_API_KEY="smoke-test-key" \
NC_LLM_MODEL="mock-model" \
nohup python3 -m nextchapter_core.api.server > /tmp/nextchapter-smoke.log 2>&1 &
PID=$!
trap "kill $PID 2>/dev/null || true" EXIT

# 等待 health
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://127.0.0.1:18432/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -sf http://127.0.0.1:18432/health >/dev/null; then
  echo "❌ sidecar 启动失败。日志："
  cat /tmp/nextchapter-smoke.log
  exit 1
fi

echo "==> /health OK"
curl -s http://127.0.0.1:18432/health | python3 -m json.tool

echo ""
echo "==> /ingest/paste OK"
RESP=$(curl -s -X POST http://127.0.0.1:18432/ingest/paste \
  -H "Content-Type: application/json" \
  -d "{\"text\": $(python3 -c 'import json; print(json.dumps(open("tests/fixtures/books/sample_novel.txt").read()))'), \"title\": \"\", \"author\": \"\"}")
echo "$RESP" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(f'  book_title: {data[\"book_title\"]}')
print(f'  author: {data[\"author\"]}')
print(f'  chapters: {len(data[\"chapters\"])}')
print(f'  first chapter: {data[\"chapters\"][0][\"title\"]}')"

echo ""
echo "✅ Smoke test 通过"
