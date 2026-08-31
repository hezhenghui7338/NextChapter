# nextchapter-core

NextChapter 的 Python sidecar 核心：导入、分段、摘要、上下文管理、续写、轻量一致性检查、风格向量。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 配置环境变量

```bash
export NC_LLM_API_KEY=your-key
export NC_LLM_PROVIDER=deepseek        # deepseek | openai | anthropic
export NC_LLM_BASE_URL=https://api.deepseek.com/v1
export NC_LLM_MODEL=deepseek-chat
```

## 启动

```bash
./scripts/run_dev.sh
# 或
python -m nextchapter_core.api.server
```

默认监听 `http://127.0.0.1:18432`，端口和 Lumina (17432) 错开。

## 模块

- `chunker` — 中文章节切分
- `summarize` — 三档摘要（fine/coarse/ultra）
- `context` — 滑动窗口 + 分级压缩
- `style` — 风格 profiler + 反 AI 味提示词
- `continue` — 续写引擎（plan_turn + generate）
- `consistency` — 轻量一致性检查（MVP）
- `llm` — LLM 客户端（OpenAI 兼容 + Anthropic）
- `api` — FastAPI HTTP 服务

## 测试

```bash
pytest
```
