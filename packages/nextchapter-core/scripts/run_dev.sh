#!/usr/bin/env bash
# 启动 sidecar（前台）。需要 NC_LLM_API_KEY。
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [ -z "$NC_LLM_API_KEY" ]; then
  echo "⚠️  NC_LLM_API_KEY 未设置。请："
  echo "    export NC_LLM_API_KEY=your-key"
  echo "    export NC_LLM_PROVIDER=deepseek   # 或 openai / anthropic"
  echo "    export NC_LLM_BASE_URL=https://api.deepseek.com/v1"
  echo "    export NC_LLM_MODEL=deepseek-chat"
  exit 1
fi

# 自动激活 venv（如果存在）
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

exec python3 -m nextchapter_core.api.server
