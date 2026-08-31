#!/usr/bin/env bash
# 端到端验证：.app bundle 里的 sidecar 能正常启动并响应请求。
# 用于 build-release 后的回归测试。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/NextChapter.app"
SIDECAR="$APP/Contents/Resources/nextchapter-core/nextchapter-core"

if [ ! -x "$SIDECAR" ]; then
  echo "❌ Sidecar 不存在：$SIDECAR"
  echo "   请先跑: bash scripts/build-release.sh"
  exit 1
fi

echo "==> 1. 直接启动 sidecar 二进制（隔离测试）..."
pkill -f nextchapter-core 2>/dev/null || true
sleep 1
(NC_LLM_API_KEY=verify-test NC_LLM_MODEL=mock-model "$SIDECAR" > /tmp/verify-sidecar.log 2>&1) &
PID=$!
trap "kill $PID 2>/dev/null || true; pkill -f nextchapter-core 2>/dev/null || true" EXIT

# 等待启动
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf http://127.0.0.1:18432/health >/dev/null 2>&1; then break; fi
  sleep 0.5
done

if ! curl -sf http://127.0.0.1:18432/health >/dev/null; then
  echo "❌ sidecar 启动失败"
  cat /tmp/verify-sidecar.log
  exit 1
fi

echo "    ✅ sidecar 启动 OK"
echo ""
echo "==> 2. /health 响应..."
curl -s http://127.0.0.1:18432/health | python3 -m json.tool
echo ""

echo "==> 3. /ingest/paste 端到端..."
TEXT=$(python3 -c 'import json; print(json.dumps(open("'"$ROOT"'/packages/nextchapter-core/tests/fixtures/books/sample_novel.txt").read()))')
RESP=$(curl -s -X POST http://127.0.0.1:18432/ingest/paste \
  -H "Content-Type: application/json" \
  -d "{\"text\": $TEXT, \"title\": \"\", \"author\": \"\"}")
echo "$RESP" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print(f'    book_title: {d[\"book_title\"]}')
print(f'    author: {d[\"author\"]}')
print(f'    chapters: {len(d[\"chapters\"])}')
print(f'    first: {d[\"chapters\"][0][\"title\"]} ({d[\"chapters\"][0][\"char_count\"]} chars)')
"

echo ""
echo "==> 4. 验证 env 变量确实传到了 sidecar（用 /health 的 llm_model 字段）..."
HEALTH=$(curl -s http://127.0.0.1:18432/health)
MODEL=$(echo "$HEALTH" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['llm_model'])")
if [ "$MODEL" = "mock-model" ]; then
  echo "    ✅ env 注入成功（model=$MODEL）"
else
  echo "    ⚠️  model=$MODEL，期望 mock-model（说明 env 没正确传入）"
  exit 1
fi

echo ""
echo "✅ 全部通过。sidecar 二进制可独立运行，env 注入工作正常。"
echo "   下一步可以: open $APP"
