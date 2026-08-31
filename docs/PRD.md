# NextChapter · 产品设计文档（PRD）

> 中文网文作者的下一章协作工具。
> 版本：v1.1 · 日期：2026-08-31 · 状态：已评审，可进入开发
>
> **v1.1 变更**：续写动线从「可选规划 + 一键续写」拆为**三选一互斥动线**——A 一键续写 / B 用户规划续写 / C AI 规划续写；`/continue/generate` 新增 `mode` 字段。详见第 10 节变更记录。

---

## 1. 背景与定位

### 1.1 背景

中文网文是高度连载化的创作形态：
- 单本常达 500-2000+ 章，单章 1500-3000 字
- 读者对剧情连贯性、世界观一致性、风格统一性极敏感
- 「AI 续写」对作者是真实痛点，但市面通用 LLM 直接续写常见三类失败：
  1. **风格跑偏**：文风突变、出现明显的「AI 味」（排比堆砌、空洞抒情、套路总结）
  2. **情节脱节**：忘记前文设定（角色身体状态、关系、伏笔），出现自相矛盾
  3. **结构失控**：字数不达标、节奏断档、爽点缺失

### 1.2 定位

**NextChapter** = 中文网文作者专用的「下一章」协作工作台。

- **不是**通用对话式 AI 写作工具
- **是**为网文作者的工作流量身设计：导入既有作品 → 让 AI 完全吃透 → 三选一动线续写（A 一键 / B 用户规划 / C AI 规划） → 风格/一致性双校验

### 1.3 参考与差异化

- **Lumina**（同作者已有项目）：本地 AI 伴读。NextChapter 沿用其 Swift macOS + Python sidecar 架构，但**完全重写网文特化逻辑**，不复用代码。
- **Sudowrite**：英文小说 AI 续写标杆。NextChapter 在「多轮规划讨论」「风格注入」「一致性检查」三处借鉴其理念，做中文网文特化。

---

## 2. 用户与场景

### 2.1 目标用户

中文网文作者（业余 / 半职业 / 职业）。已有成稿作品，正在连载或准备开新书。

### 2.2 核心使用场景

| 场景 | 描述 |
| --- | --- |
| **新书开坑** | 作者完成 20-30 章开篇后导入，让 AI 吃透世界观与人设，再开始辅助续写 |
| **日常更新** | 每天续写 1-3 章，与 AI 讨论下一章走向，AI 生成，作者调整后发布 |
| **卡文求助** | 卡在某章时，让 AI 给出多种剧情走向（爽点 / 节奏 / 填坑）供选择 |
| **续写接手** | 老作者接手他人作品（需授权），导入前文后即可让 AI 续写 |

### 2.3 用户故事

1. 作为作者，我**导入整本网文（TXT 或粘贴）**，系统自动按章节切分，识别书名/作者。
2. 系统**自动分析全书**：对每章生成细摘要 → 对最近 25 章做滑动窗口摘要 → 抽取作者风格向量。
3. 我**点击「开始续章」**，选择下一章标题（比如「第 388 章」）和目标字数。
4. 我**选择一种续写动线**（**三选一、互斥**）：
   - **A. 一键续写**——直接出章。AI 基于上下文和风格即兴发挥，**完全不规划**。适合日常更新、剧情不卡时。
   - **B. 用户规划续写**——我自己在输入框里拟定下一章的剧情纲要 / 关键场景 / 爽点 / 节奏 / 坑点（结构化 5 维），AI **严格按我的规划写，不擅自发散**。适合已有腹稿、想严格控制剧情走向时。
   - **C. AI 规划续写**——**入口是「让 AI 出一份规划初稿」（一键触发，不是用户先打字）**。AI 出完初稿后进入「可编辑」状态：用户可以直接编辑初稿，也可以展开「和 AI 讨论」面板继续 plan_turn 多轮讨论。满意后点**「锁定规划」**（把当前文本存为 final_plan），最后点**「按规划续写」**生成正文。适合卡文、想多碰撞几条思路时。
5. AI 生成下一章正文，系统**自动做一致性检查**，列出可能与前文冲突的地方。
6. 我**编辑或重生成**，满意后保存到本机。
7. 当我**自己续写了几章**后，再次导入新章节，系统做增量分析。

---

## 3. 功能需求

### 3.1 MVP 功能清单

| 编号 | 功能 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| F1 | TXT 文件导入 | P0 | 正确按「第X章」切分；空章节或短章节（<80字）合并到上一章 |
| F2 | 粘贴导入 | P0 | 自动识别《书名》/作者行；正确切分章节 |
| F3 | 单章细摘要（400 字） | P0 | 覆盖核心事件、人物、悬念 |
| F4 | 中期粗摘要（150 字） | P0 | 保留核心冲突、关键转折、伏笔 |
| F5 | 远端极简摘要（60 字） | P0 | 一句话浓缩核心推进 |
| F6 | 25 章滑动窗口 + 短书降级 | P0 | 短书（≤25 章）全部细摘要；长书按 5+10+10 分级 |
| F7 | 风格向量抽取 | P0 | 从前 3 章抽 few-shot + LLM 抽风格描述 |
| F8 | 反 AI 味提示词 | P0 | 3 档强度（mild / default / strong），注入续写 prompt |
| F9 | 多轮规划讨论 | P0 | 用户与 AI 围绕 5 维度（剧情/爽点/节奏/坑点/填坑）对话，主要服务于 **C 动线**（AI 规划续写）的审阅 / 讨论环节；B 动线下也可作为「AI 帮我打磨我的规划」的可选辅助；**A 动线下不出现此功能** |
| F10a | 一键续写（A 动线） | P0 | **不规划、不讨论**；仅依据上下文 + 风格 + 反 AI 味 + 目标字数生成下一章正文，AI 即兴发挥；UI 提供「点一下出章」的最短路径；目标用户：日常更新、剧情不卡时 |
| F10b | 用户规划续写（B 动线） | P0 | 用户在 UI 提供「下一章规划」文本（含剧情走向、关键场景、爽点、节奏、坑点五维），AI **严格按规划写**；如偏离需在正文中显式标注为「规划外的内容」由用户决定取舍；目标用户：已有腹稿、想严格控制剧情时 |
| F10c | AI 规划续写（C 动线） | P0 | 入口一键触发，AI 自动出 5 维规划初稿；用户可编辑、可选「和 AI 讨论」多轮迭代；满意后点「锁定规划」存为 final_plan，再点「按规划续写」生成正文。讨论面板的 AI 回复不自动覆盖初稿，需手动合并，避免误覆盖。目标用户：卡文、想多碰撞思路时 |
| F10d | 动线选择 UX | P0 | 续写主视图默认三选一动线作为**互斥 radio**（A / B / C），切换动线时清空当前阶段的中间态（未锁定规划 / 用户已填规划 / 讨论历史），避免状态串台 |
| F11 | 字数控制 | P0 | 目标字数 500-5000 可调；不做硬性截断（生成时给目标区间） |
| F12 | 轻量一致性检查 | P0 | 续写后用 LLM 单次扫描冲突：人物（年龄/状态/生死/能力）、世界（地点/规则/势力）、剧情（已发生/未解决/伏笔） |
| F13 | 增量导入 | P1 | 检测新增章节，做增量分析；保留原摘要 |
| F14 | 完整 fact-bank 一致性 | P1 | 独立事实库（人物档案、设定、未解事件）+ 主动校验 + 续写前预检 |
| F15 | 导出 | P2 | 续写结果导出为 TXT/Markdown |
| F16 | 多作品管理 | P1 | 书架视图支持多本书、独立分析 |

### 3.2 非功能需求

| 类别 | 要求 |
| --- | --- |
| 性能 | 200 章作品首次完整分析 ≤ 5 分钟（DeepSeek API 速率下） |
| 隐私 | 文本与笔记仅存本机；云端 LLM 调用时**只传**必要的摘要/上下文/请求正文 |
| 成本 | 单章续写（2000 字）DeepSeek 成本 ≤ ¥0.05 |
| 平台 | macOS 14+（MVP）；Windows 在 P2 评估 |
| 离线 | 不支持（MVP 必须联网云端 LLM） |

---

## 4. 架构

### 4.1 总体架构

```
┌──────────────────────┐       HTTP (localhost:18432)      ┌──────────────────────┐
│   macOS App (Swift)  │  ──────────────────────────────►  │  Python Sidecar      │
│   SwiftUI            │                                    │  FastAPI             │
│                      │  ◄──────────────────────────────   │                      │
└──────────────────────┘                                    │  ┌────────────────┐  │
         │                                                  │  │ chunker        │  │
         │                                                  │  │ summarize      │  │
         │                                                  │  │ context        │  │
         │                                                  │  │ style          │  │
         │                                                  │  │ writing        │  │
         ▼                                                  │  │ consistency    │  │
   本机存储：用户偏好/书架/草稿                                   │  └────────────────┘  │
   ~/Library/Application Support/NextChapter/                 │         │             │
                                                            │         ▼             │
                                                            │   云端 LLM API         │
                                                            │   (DeepSeek/OpenAI/   │
                                                            │    Anthropic)          │
                                                            └──────────────────────┘
```

### 4.2 选型与决策

| 决策点 | 选择 | 理由 |
| --- | --- | --- |
| 技术栈 | Swift macOS app + Python sidecar（沿用 Lumina 架构） | 与 Lumina 一致；分段/摘要/风格逻辑 Python 实现更高效 |
| LLM 后端 | 云端 API 优先（DeepSeek/OpenAI/Anthropic） | 中文网文质量云端显著优于本地；DeepSeek 性价比最高 |
| 复用策略 | **借鉴思路，重写网文特化版** | 不与 Lumina 代码耦合；迭代自由 |
| 上下文策略 | 25 章滑动窗口 + 5/10/10 分级 | 短书全部细摘要（保留全信息）；长书按远→近分级压缩 |
| 风格实现 | 风格向量 + 反 AI 味提示词 | few-shot 样本 + LLM 抽风格描述 + 反 AI 约束叠加 |
| 一致性 | MVP 轻量版（LLM 单次扫描），P1 完整 fact-bank | MVP 验证核心价值，P1 解决复杂场景 |
| 导入格式 | TXT + 粘贴 | 覆盖 95%+ 网文场景；EPUB 等放 P2 |
| 字数 | 目标区间，不做硬性截断 | 网文字数弹性大，硬性截断会破坏语义 |
| 开发顺序 | 先骨架（已完成）→ 端到端联调 → 单元测试覆盖 | 验证价值优先，测试保障回归 |

### 4.3 模块职责

**Python sidecar**（`packages/nextchapter-core/`）：

| 模块 | 职责 |
| --- | --- |
| `ingest` | TXT/粘贴导入，解析书名/作者 |
| `chunker` | 中文章节切分；识别「第X章/卷/序/楔子/番外」 |
| `summarize` | 三档摘要（fine 400 / coarse 150 / ultra 60 字符） |
| `context` | 25 章滑动窗口 + 短书降级 + prompt 拼装 |
| `style` | 风格向量（few-shot + LLM 描述）+ 反 AI 味提示词 |
| `writing` | 续写引擎：plan_turn（多轮讨论，服务于 C 动线）+ generate（按 `mode` 处理 A/B/C 三种动线） |
| `consistency` | 轻量一致性检查：续写后 LLM 扫描冲突 |
| `llm` | 云端 LLM 客户端：OpenAI 兼容 + Anthropic |
| `api` | FastAPI 服务（9 个端点） |

**Swift app**（`apps/macos/NextChapter/`）：

| 模块 | 职责 |
| --- | --- |
| `NextChapterApp` | App 入口，启动 sidecar |
| `Services/SidecarManager` | Python 子进程生命周期管理 |
| `Services/CoreClient` | HTTP 客户端 |
| `Services/AppSettings` | API key / provider / 模型 / 窗口配置 |
| `Models/Book` | 本机书架模型 + 持久化 |
| `Features/Library` | 书架视图：导入 / 列表 / 详情 / 触发分析 |
| `Features/Continue` | 续写主视图：选书 → 选择 A/B/C 三选一动线 → 走对应流程 → 一致性检查（动线间互斥，切换清空中间态） |
| `Features/Settings` | 设置：API key / 上下文窗口 / 反 AI 味强度 / sidecar 重启 |

### 4.4 端到端流程

> 续写部分拆为**三条互斥动线**（A / B / C），前置导入分析和后置一致性检查、编辑为共用流程。

#### 4.4.1 导入 + 分析（共用前置）

```
用户                            Swift App                       Sidecar                     LLM
 │  导入 TXT/粘贴        │                              │                       │
 ├──────────────────────►│  POST /ingest/paste         │                       │
 │                       ├────────────────────────────►│  chunker.split()       │
 │                       │◄─────────── chapters ───────│                       │
 │                       │                              │                       │
 │  点击「开始分析」       │                              │                       │
 ├──────────────────────►│  POST /style                │                       │
 │                       ├────────────────────────────►│  LLM 抽风格描述         │
 │                       │                              ├──────────────────────►│
 │                       │                              │◄──── style profile ──│
 │                       │  POST /summarize (fine)     │                       │
 │                       ├────────────────────────────►│  LLM 逐章摘要           │
 │                       │                              ├──────────────────────►│
 │                       │                              │◄──── summaries ──────│
 │                       │◄──── fine summaries ────────│                       │
```

#### 4.4.2 续写（三选一动线）

进入「续写」视图后，用户**必须三选一**确定动线，再走对应支线。动线之间互斥，切换时清空中间态。

**A 动线 · 一键续写**——完全不规划，点一下出章

```
用户                            Swift App                       Sidecar                     LLM
 │  选 A 动线 + 输目标字数        │                              │                       │
 ├─────────────────────────────►│  POST /continue/generate    │                       │
 │                              │  {mode: "auto",              │                       │
 │                              │   final_plan: null,          │                       │
 │                              │   context_text, style_text}  │                       │
 │                              ├─────────────────────────────►│  拼装 context+style+反 AI 味 │
 │                              │                              ├──────────────────────►│
 │                              │                              │◄──── chapter body ───│
 │                              │◄──────── chapter ─────────────│                       │
```

**B 动线 · 用户规划续写**——自己写规划，AI 照写

```
用户                            Swift App                       Sidecar                     LLM
 │  选 B 动线                    │                              │                       │
 │  填规划（5 维结构化输入）      │                              │                       │
 │  剧情走向 / 关键场景 /          │                              │                       │
 │  爽点 / 节奏 / 坑点            │                              │                       │
 ├─────────────────────────────►│  POST /continue/generate    │                       │
 │                              │  {mode: "user_plan",         │                       │
 │                              │   final_plan: "...",         │                       │
 │                              │   context_text, style_text}  │                       │
 │                              ├─────────────────────────────►│  拼装 context+style+规划 │
 │                              │                              ├──────────────────────►│
 │                              │                              │  严格按规划生成正文      │
 │                              │                              │◄──── chapter body ───│
 │                              │◄──────── chapter ─────────────│                       │
```

**C 动线 · AI 规划续写**——AI 先出规划，多轮讨论后 AI 写

```
用户                            Swift App                       Sidecar                     LLM
 │  选 C 动线                    │                              │                       │
 │  「请给下一章规划」            │  POST /continue/plan_turn   │                       │
 ├─────────────────────────────►├─────────────────────────────►│  LLM 出规划初稿         │
 │                              │                              ├──────────────────────►│
 │                              │                              │◄──── assistant msg ───│
 │                              │◄──────── assistant ───────────│                       │
 │  审阅 / 编辑 / 继续讨论（×N）  │  POST /continue/plan_turn   │  复用 F9 5 维讨论        │
 │                              ├─────────────────────────────►├──────────────────────►│
 │                              │                              │◄──── assistant msg ───│
 │                              │◄──────── assistant ───────────│                       │
 │  点击「锁定规划」              │                              │                       │
 ├─────────────────────────────►│  POST /continue/generate    │                       │
 │                              │  {mode: "ai_plan",           │                       │
 │                              │   final_plan: "讨论后纲要",   │                       │
 │                              │   context_text, style_text}  │                       │
 │                              ├─────────────────────────────►│  拼装 context+style+最终规划 │
 │                              │                              ├──────────────────────►│
 │                              │                              │◄──── chapter body ───│
 │                              │◄──────── chapter ─────────────│                       │
```

#### 4.4.3 一致性检查 + 编辑（共用后置）

```
用户                            Swift App                       Sidecar                     LLM
 │  点击「一致性检查」  │  POST /consistency/check    │  LLM 扫描冲突          │
 ├─────────────────────►├────────────────────────────►├──────────────────────►│
 │                       │                            │◄──── issues list ────│
 │                       │◄──── issues ────────────────│                       │
 │  编辑/重生成           │                            │                       │
```

---

## 5. 数据模型

### 5.1 本机持久化

```
~/Library/Application Support/NextChapter/
├── books.json                    # 书架列表（每本书的元数据 + 摘要 + 风格）
└── settings.json                 # AppSettings 备份
```

### 5.2 Book 模型

```json
{
  "id": "uuid",
  "title": "书名",
  "author": "作者",
  "raw_text": "原始正文（用于增量导入）",
  "chapters": [
    {"index": 0, "title": "第一章 X", "body": "...", "char_count": 2000, "kind": "chapter"}
  ],
  "summaries": [
    {"chapter_index": 0, "title": "第一章 X", "tier": "fine", "text": "..."}
  ],
  "style_description": "句长偏好...",
  "anti_ai_directive": "1. 避免排比...",
  "style_samples": ["原文片段1", "原文片段2", "原文片段3"],
  "created_at": "2026-08-31T...",
  "updated_at": "2026-08-31T..."
}
```

---

## 6. API 契约（Sidecar）

| 端点 | 方法 | 请求 | 响应 | 说明 |
| --- | --- | --- | --- | --- |
| `/health` | GET | — | `{status, version, pid, llm_provider, llm_model}` | 健康检查 |
| `/ingest/path` | POST | `{path}` | `ImportResponse` | 从文件路径导入 |
| `/ingest/paste` | POST | `{text, title, author}` | `ImportResponse` | 粘贴导入 |
| `/summarize` | POST | `{book_title, chapters, tier, indices?}` | `{summaries}` | 摘要生成 |
| `/style` | POST | `{book_title, samples}` | `{description, anti_ai_directive, samples}` | 风格抽取 |
| `/context/build` | POST | `{summaries, total_chapters}` | `{rendered, fine_count, coarse_count, ultra_count}` | 滑动窗口拼装 |
| `/continue/plan_turn` | POST | `{book_title, next_chapter_hint, user_message, history, context_text, style_text}` | `{assistant}` | 规划讨论（主要服务于 C 动线；B 动线可作为辅助打磨） |
| `/continue/generate` | POST | `{book_title, next_chapter_hint, target_chars, mode, final_plan, history, context_text, style_text}` | `{chapter_title, body, char_count}` | 续写主端点。`mode` ∈ {`auto` (A 动线，final_plan 必须为空) / `user_plan` (B 动线，final_plan 必填，源自用户输入) / `ai_plan` (C 动线，final_plan 必填，源自 plan_turn 讨论)} |
| `/consistency/check` | POST | `{known_context, new_chapter}` | `{is_clean, summary, issues[]}` | 一致性检查 |

---

## 7. 测试策略

### 7.1 测试分层

| 层级 | 范围 | 工具 | 触发 |
| --- | --- | --- | --- |
| **单元测试** | 纯 Python 逻辑（chunker / context window / style profiler / consistency JSON 解析 / 配置加载） | pytest | 每次 commit |
| **端到端测试** | 完整流程通过 FastAPI TestClient（导入 → 摘要 → 上下文 → 续写 → 一致性） | pytest + Mock LLM Router | 每次 commit |
| **Live 测试** | 真实 DeepSeek API 跑通（需 API key） | pytest `-m live` | 手动 / 每周 |
| **手动验收** | Swift UI 真实交互 | 人工 | 每次发版前 |

### 7.2 Mock 策略

- **不调用真实 LLM**：所有端到端测试用 `MockLLMRouter`，按 prompt 关键词返回预录响应。
- **Fixtures**：
  - `tests/fixtures/books/`：真实网文片段（去敏）
  - `tests/fixtures/llm/`：按 prompt hash 缓存的 mock 响应
- **Live 测试**：`pytest -m live` 标记，需要 `NC_LLM_API_KEY` 环境变量；不在常规 CI 跑。

### 7.3 关键测试用例

详见 `tests/e2e/test_full_flow.py` 与 `tests/unit/`。

---

## 8. 风险与限制

| 风险 | 缓解措施 |
| --- | --- |
| DeepSeek 长上下文质量不稳定 | 25 章窗口限制；续写只用最近 5 章细摘要 + 远端压缩 |
| 一致性检查漏报/误报 | MVP 接受漏报优先（避免误报打扰用户）；P1 fact-bank 提升覆盖率 |
| 增量导入与原摘要冲突 | 简单策略：新增章节全量重摘要老章节；P1 优化为按章节增量 |
| 风格向量在长书（500+章）失效 | 限制 few-shot 取最近 3 章；P1 引入分层风格（开篇/中段/结尾） |
| 用户输入「AI 味」描述的网文 | 反 AI 味 prompt 主动避免；P1 加 AI 生成文本检测器辅助 |

---

## 9. 路线图

| 阶段 | 时间 | 交付 |
| --- | --- | --- |
| **Phase 0** 骨架 | ✅ 已完成 | 项目结构 + Python sidecar + Swift app 编译通过 |
| **Phase 1** 核心流程 | 1-2 周 | TXT 导入 → 章节切分 → 三档摘要 → 风格抽取（端到端可用，需真实 API key 验证） |
| **Phase 2** 续写主流程 | 1-2 周 | 三选一动线（A 一键 / B 用户规划 / C AI 规划）+ 轻量一致性检查；端到端测试覆盖三种动线各 ≥1 路径 |
| **Phase 3** 增量 + 体验 | 1 周 | 增量导入、UI 打磨、错误恢复 |
| **P1** fact-bank | 1-2 周 | 独立事实库 + 续写前预检 + 完整一致性 |
| **P2** 多平台 | 2-3 周 | Windows 版本、导出、更多格式 |

---

## 10. 变更记录

| 版本 | 日期 | 变更 | 作者 |
| --- | --- | --- | --- |
| v1.0 | 2026-08-31 | 基于讨论正式化 PRD（原 RAW_PRD.md 保留为 PRD-draft.md） | — |
| v1.1 | 2026-08-31 | 续写动线从「可选规划 + 一键续写」拆为**三选一互斥动线**（A 一键 / B 用户规划 / C AI 规划）；F9 重定位为 C 动线服务；新增 F10a/b/c/d；`/continue/generate` 新增 `mode` 字段；4.4 端到端流程重排为 4.4.1 前置 / 4.4.2 三动线 / 4.4.3 后置 | — |

---

## 附录 A：决策记录

源自用户与 Mavis 的产品讨论，2026-08-31：

1. **架构**：沿用 Lumina（Swift + Python sidecar），不复用模块
2. **LLM**：云端 API 优先（DeepSeek/Claude）
3. **复用粒度**：借鉴思路，重写网文特化版
4. **上下文**：25 章滑动窗口 + 5/10/10 分级（短书全部 fine）
5. **风格**：风格向量 + 反 AI 味提示词
6. **一致性**：MVP 轻量版，P1 完整
7. **格式**：TXT + 粘贴
8. **字数**：灵活，不硬性
9. **起步**：先搭骨架，再端到端联调（已完成骨架，进入 Phase 1）
