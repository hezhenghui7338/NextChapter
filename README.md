<p align="center">
  <img src="docs/assets/logo.png" alt="NextChapter — 续章" width="640">
</p>

<p align="center">
  <strong>中文网文 AI 续写助手</strong><br>
  导入你的网文 → 自动分析 → 选 A/B/C 续写动线 → 出章
</p>

> 架构沿用 [Lumina](https://github.com/hezhenghui7338/Lumina)（Swift macOS app + Python sidecar），但完全重写网文特化逻辑。

## 特性（目标）

- **TXT / 粘贴导入**：支持中文章节切分（`第X章` / `卷X` / `序` / `楔子` / `番外`）
- **滚动摘要**：每章细摘要 → 中期粗摘要 → 远端一句话压缩（25 章窗口滑动）
- **风格向量**：从作者前 N 章抽取 few-shot + LLM 抽风格描述 + 反 AI 味提示词
- **三选一动线**：A 一键续写（不规划，点一下出章）/ B 用户规划续写（自己写纲要，AI 照写）/ C AI 规划续写（AI 先出规划，多轮讨论后锁定再写）—— 续写主视图把三条动线做成互斥 radio，按需选
- **规划讨论（C 动线）**：点「让 AI 出一份规划初稿」一键触发，AI 出 5 维初稿后可编辑、可展开讨论面板多轮改写，满意后「锁定规划」再生成正文
- **轻量一致性检查**：续写后用 LLM 扫描与前文的冲突（人物/世界/剧情）
- **增量导入**：用户续写了几章后再次导入，自动增量分析

## 项目结构

```
NextChapter/
├── apps/macos/                # Swift macOS app（SwiftUI）
│   ├── Package.swift
│   └── NextChapter/
│       ├── NextChapterApp.swift
│       ├── ContentView.swift
│       ├── Services/          # SidecarManager / CoreClient / AppSettings
│       ├── Models/            # Book / BookStore
│       └── Features/          # Library / Continue / Settings
└── packages/nextchapter-core/ # Python sidecar（FastAPI）
    ├── nextchapter_core/
    │   ├── chunker/           # 中文章节切分
    │   ├── summarize/         # 三档摘要
    │   ├── context/           # 25 章滑动窗口
    │   ├── style/             # 风格向量 + 反 AI 味
    │   ├── writing/           # 续写引擎（避免与 Python 关键字冲突）
    │   ├── consistency/       # 轻量一致性检查
    │   ├── llm/               # LLM 客户端（DeepSeek/OpenAI/Anthropic）
    │   └── api/               # FastAPI HTTP 服务
    ├── scripts/run_dev.sh
    └── tests/
```

## 开发

### 1) 准备 Python 侧

```bash
cd packages/nextchapter-core
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 设置 LLM key
export NC_LLM_API_KEY=sk-xxx
export NC_LLM_PROVIDER=deepseek
export NC_LLM_BASE_URL=https://api.deepseek.com/v1
export NC_LLM_MODEL=deepseek-chat

# 跑测试
pytest

# 启动 sidecar
python -m nextchapter_core.api.server
# → http://127.0.0.1:18432
```

### 2) 启动 macOS app

```bash
cd apps/macos
swift run
```

Swift app 会自动检测 sidecar 是否在 18432 端口运行，没有就启动。

### 3) 端到端联通验证

```bash
# 终端 1
cd packages/nextchapter-core && source .venv/bin/activate
python -m nextchapter_core.api.server

# 终端 2
curl http://127.0.0.1:18432/health
# → {"status":"ok",...}

curl -X POST http://127.0.0.1:18432/ingest/paste \
  -H "Content-Type: application/json" \
  -d '{"text":"《测试》\n作者：X\n\n第一章 ...\n\n第二章 ...","title":"","author":""}'
```

## API 端点（sidecar）

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/health` | GET | 健康检查 |
| `/ingest/path` | POST | 从文件路径导入（TXT） |
| `/ingest/paste` | POST | 粘贴导入 |
| `/summarize` | POST | 对章节列表做摘要（tier: fine / coarse / ultra） |
| `/style` | POST | 从前 N 章抽取风格向量 + 反 AI 味 |
| `/context/build` | POST | 从摘要列表构建 25 章分级窗口 |
| `/continue/plan_turn` | POST | 与 AI 多轮讨论下一章规划（C 动线主用） |
| `/continue/generate` | POST | 续写主端点；请求体含 `mode`：`auto`（A 动线） / `user_plan`（B 动线） / `ai_plan`（C 动线） |
| `/consistency/check` | POST | 对续写结果做一致性扫描 |

## 决策摘要

| 决策 | 选择 |
| --- | --- |
| 技术栈 | 沿用 Lumina 架构（Swift + Python sidecar），不复制模块 |
| LLM 后端 | 云端 API 优先（DeepSeek / OpenAI / Anthropic） |
| 复用策略 | 借鉴思路，重写网文特化版 |
| 上下文 | 25 章滑动窗口 + 5/10/10 分级（短书全部 fine） |
| 风格 | 风格向量 + 反 AI 味提示词（3 档强度） |
| 一致性检查 | MVP 轻量版（LLM 单次扫描），完整 fact-bank 放 P1 |
| 导入格式 | TXT + 粘贴 |
| 字数 | 不做硬性约束（生成时给目标区间，可在 UI 调） |

## 路线图

- [x] Phase 0 — 项目骨架 + Python sidecar + LLM 客户端
- [x] Phase 0 — Swift macOS 编译通过
- [ ] Phase 1 — 完整跑通：导入 → 章节切分 → 三档摘要 → 风格提取
- [ ] Phase 2 — 续写主流程：三选一动线（A 一键 / B 用户规划 / C AI 规划）→ 一致性检查
- [ ] Phase 3 — 增量导入（用户自己写了几章后再次导入）
- [ ] P1 — 完整 fact-bank 一致性检查（独立事实库 + 主动校验）
- [ ] P1 — 离线缓存：导入后保留 chunker/summarize 状态，二次启动秒开
