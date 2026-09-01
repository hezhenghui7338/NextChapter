# NextChapter · 面试作品提交说明

> 中文网文 AI 续写助手（macOS 原生应用）  
> 提交日期：2026-08-31

---

## 1. 产品链接与体验说明

### 产品形态说明

NextChapter 是 **macOS 14+ 桌面应用**（非 Web），无浏览器端。可访问的「线上产物」为 GitHub 公开发布的安装包：

| 资源 | 链接 |
| --- | --- |
| **最新 Release（推荐）** | https://github.com/hezhenghui7338/NextChapter/releases/latest |
| **v0.1.0 DMG 直链** | https://github.com/hezhenghui7338/NextChapter/releases/download/v0.1.0/NextChapter-0.1.0-macOS.dmg |
| **Git 仓库** | https://github.com/hezhenghui7338/NextChapter |

**系统要求：** macOS 14.0+ · Apple Silicon / Intel · 需联网（调用云端 LLM）· 安装包约 43 MB，**无需单独安装 Python**。

### 5 分钟快速体验路径（建议录屏按此走）

> 体验前请自备 LLM API Key（推荐 [DeepSeek](https://platform.deepseek.com/)，性价比高）。Key 仅存本机，不上传。

1. **下载安装** — 打开 Release 页，下载 DMG，将 `NextChapter.app` 拖入 Applications 并启动。
2. **配置 LLM** — 进入 **设置** Tab，填写 Provider / API Key / Model（如 `deepseek-chat`），反 AI 味强度保持默认即可。
3. **导入作品** — **书库** Tab → **文档导入** 或 **粘贴导入**（准备一份 `.txt` 网文，含 `第X章` 标题格式；10–30 章即可快速跑通）。
4. **开始分析** — 选中作品 → 点 **「开始分析」**，等待风格抽取 + 逐章摘要完成（章数越多耗时越长，10 章约 2–5 分钟）。
5. **续章出稿** — 切 **续章** Tab → 填下一章标题与目标字数 → 三选一动线任选其一：
   - **A · 一键续写** — 日常更新，点一下出章（录屏建议演示此条，路径最短）
   - **B · 按我的规划续写** — 填 5 维规划，AI 严格照写
   - **C · AI 规划续写** — AI 出规划初稿 → 讨论/编辑 → 锁定 → 续写
6. **审阅收章** — 对生成结果试 **一致性检查** 或 **AI 重写**，满意后 **采纳加入原文** 或 **复制**。

### 无 macOS 时的替代验证

- 阅读 [README 产品体验章节](https://github.com/hezhenghui7338/NextChapter#产品体验) 与 [PRD](https://github.com/hezhenghui7338/NextChapter/blob/main/docs/PRD.md)
- 本地源码跑通（见 README「开发者」节）：`just install && export NC_LLM_API_KEY=sk-xxx && just dev`
- 跑测试（无需 API Key）：`just test`（93 项单元 + E2E，mock LLM）

---

## 2. Git 仓库

**https://github.com/hezhenghui7338/NextChapter**

README 已包含完整运行说明：

- **用户侧：** Release 下载 → 设置 API Key → 导入 → 分析 → 续章
- **开发者侧：** `just install` / `just dev` / `just test` / `just release`

---

## 3. 汇报录屏脚本（≤ 5 分钟）

> 建议结构：问题 45s → 演示 2min → 关键选择 1min → AI 协作 45s → 边界与时间 30s

### 0:00–0:45 · 我解决了什么问题

「中文网文作者连载时常遇到三类 AI 续写失败：**风格跑偏**（AI 味重）、**情节脱节**（忘记前文设定）、**结构失控**（字数/节奏/爽点不对）。通用 Chat 式写作工具不理解网文工作流——作者已有几十到上千章成稿，需要的是**接续既有文风与剧情**，而不是从零胡写。

NextChapter 的定位是**中文网文专用的下一章协作工作台**：导入整本书 → 让 AI 吃透前文 → 三选一动线出下一章 → 一致性校验。」

### 0:45–2:45 · 产品演示（核心 2 分钟）

按「体验路径」操作，重点展示：

1. 设置页配 Key（一闪而过，强调 Key 仅存本机）
2. 导入 TXT，自动切章
3. **开始分析** → 章节列表出现摘要（说明：三档滚动摘要 + 25 章滑动窗口）
4. 续章 Tab → **A 一键续写** 生成一章
5. 点 **一致性检查**，展示冲突扫描结果
6. （可选 15s）快速切到 C 动线，展示 AI 规划初稿

### 2:45–3:45 · 关键技术与产品选择

| 选择 | 理由 |
| --- | --- |
| **Swift macOS + Python sidecar** | 沿用自研 Lumina 架构：SwiftUI 做原生体验，Python 承载 NLP/LLM 管线；sidecar 随 App 打包，用户零配置 |
| **云端 LLM 优先（DeepSeek 等）** | 中文网文续写质量云端显著优于本地小模型；API Key 用户自备，降低合规与成本 |
| **25 章滑动窗口 + 三档摘要（细/粗/极简）** | 长书不可能全量塞 context；近章保细节、远章压缩，在 token 预算内最大化连贯性 |
| **三选一动线（A/B/C 互斥）** | 对应真实作者状态：顺畅日常更新 / 有腹稿要控剧情 / 卡文要碰撞思路；互斥避免动线串台 |
| **MVP 轻量一致性检查 → P1 fact-bank** | 先单次 LLM 扫描人物/世界/剧情冲突，快速可用；完整事实库留 Phase 3 |

### 3:45–4:30 · AI 如何参与开发

「本项目是 **AI 原生开发** 的典型实践，Cursor Agent 贯穿全流程：

1. **产品设计** — 从 PRD-draft 讨论出完整 PRD（含三动线互斥、API 契约、验收标准）；AI 辅助竞品对标（Sudowrite）与网文场景拆解
2. **架构与实现** — AI 生成 Python sidecar（切分/摘要/上下文/续写/一致性）与 SwiftUI 三 Tab 界面；人负责方向拍板与联调验收
3. **测试与发版** — AI 编写 93 项单元/E2E 测试（mock LLM）；`build-release.sh` 一键 PyInstaller + Swift release → DMG/ZIP
4. **迭代修复** — v0.1.1 修复推理模型空正文、摘要章数显示等，AI 定位 + 补丁

**人的角色：** 定产品边界、评审 PRD、验证续写质量、决定哪些 AI 产出可合并。AI 负责大量样板代码、测试与文档，显著压缩从 0 到可发布版本的周期。」

### 4:30–5:00 · 完成边界与实际投入

**已完成（v0.1.1）：**

- Phase 0–2：导入 → 切分 → 三档摘要 → 风格向量 → 三动线续写 → 轻量一致性 + AI 重写
- macOS 公开发版（DMG/ZIP）、README 体验文档、93 项测试

**未完成 / 路线图：**

- Phase 3：增量导入体验打磨、分析结果缓存秒开
- P1：完整 fact-bank 一致性（独立事实库 + 续写前预检）
- P2：Windows、EPUB 导入

**实际投入时间：** 约 **1 个工作日**（2026-08-31，含 PRD 评审、端到端开发、测试、打包发版）。AI 辅助将 PRD 中预估 3–5 周的工作量压缩到单日可交付 MVP；其中约 60% 时间为产品决策与续写质量人工验收，40% 为 AI 协作编码与联调。

---

## 4. 一页纸摘要（可直接粘贴到提交表单）

```
【项目名称】NextChapter — 中文网文 AI 续写助手

【产品链接】https://github.com/hezhenghui7338/NextChapter/releases/latest
（macOS 14+ 桌面应用，下载 DMG 安装；需自备 DeepSeek/OpenAI 等 API Key）

【Git 仓库】https://github.com/hezhenghui7338/NextChapter
（README 含用户安装说明与开发者 just dev/test/release 命令）

【解决的问题】
通用 LLM 续写网文时风格跑偏、情节脱节、结构失控。NextChapter 为连载作者设计：
导入成稿 → 三档摘要 + 25 章滑动窗口让 AI 吃透前文 → A/B/C 三选一动线出下一章 → 一致性检查。

【关键选择】
Swift+Python sidecar 原生 macOS；云端 LLM；三档滚动摘要控 token；三动线互斥对应日常/控剧情/卡文场景。

【AI 参与开发】
Cursor Agent 全流程：PRD 结构化、sidecar+SwiftUI 实现、93 项测试、发版脚本与文档；人负责产品边界与续写质量验收。

【完成边界】
✅ 导入/分析/三动线续写/一致性/AI 重写/macOS 发版
⬜ fact-bank 完整一致性、Windows、EPUB、分析缓存

【投入时间】约 1 工作日（AI 辅助压缩传统 3–5 周 MVP 周期）
```

---

## 5. 录屏提交清单

- [x] 录屏文件（≤ 5 分钟，建议 1080p，含系统声音/旁白）→ [`docs/NextChapter-submission.mp4`](NextChapter-submission.mp4)（约 4:08，1080p + 中文旁白）
- [ ] 本仓库链接 + Release 链接
- [ ] 若面试官无 macOS：附 README 截图或测试报告（`just test` 输出）
