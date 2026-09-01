"""续写引擎。

三个模式：
1. plan_turn: 与用户多轮讨论下一章规划（剧情/爽点/节奏/坑点）
2. generate: 依据规划 + 上下文 + 风格 → 生成下一章正文
3. critique: 对已生成的草稿给修改意见 + 建议重写版

字数以用户设置的目标为准，允许 ±30% 浮动；通过 max_tokens 约束生成长度，
超长时在句/段边界兜底截断（与 plan_draft 同理）。

generate 阶段支持三种互斥动线（PRD F10a/b/c）：
- AUTO       A 动线：完全不规划，AI 基于上下文即兴
- USER_PLAN  B 动线：用户自己写规划，AI 严格按规划写
- AI_PLAN    C 动线：AI 起草 → 多轮讨论 → 用户锁定 → AI 按最终规划写
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..context import WindowedContext
from ..llm import LLMClient, LLMMessage
from ..style import StyleProfile, StyleProfiler

log = logging.getLogger("nextchapter.continue")

# C 动线 plan_draft：规划初稿硬性字数上限（含标点）
PLAN_DRAFT_MAX_CHARS = 200

# 续写正文：相对 target_chars 的浮动上限（PRD F11：±30%）
GENERATE_CHAR_FLOAT_RATIO = 1.3


class ContinueMode(str, Enum):
    """续写动线（PRD F10a/b/c）。"""

    AUTO = "auto"            # A 动线：一键续写
    USER_PLAN = "user_plan"  # B 动线：用户规划续写
    AI_PLAN = "ai_plan"      # C 动线：AI 规划续写


@dataclass
class PlanningTurn:
    role: str  # user | assistant
    content: str


@dataclass
class ContinueRequest:
    book_title: str
    next_chapter_hint: str  # 第 X 章
    target_chars: int = 2000  # 默认 2000，不是硬性约束
    mode: ContinueMode = ContinueMode.AUTO
    planning_history: List[PlanningTurn] = field(default_factory=list)
    context: Optional[WindowedContext] = None
    style: Optional[StyleProfile] = None
    # 用户的最终规划（在多轮讨论后由用户确认的关键剧情走向）
    # AUTO 模式必须为空；USER_PLAN / AI_PLAN 模式必填
    final_plan: str = ""


@dataclass
class ContinueResult:
    chapter_title: str
    body: str
    char_count: int
    raw_response: str = ""
    # "stop" | "length" — length 表示被 max_tokens 截断（已尝试自动续写）
    finish_reason: str = "stop"


@dataclass
class CritiqueIssue:
    category: str       # plot | character | prose | pacing | ai_smell | consistency | other
    severity: str       # high | medium | low
    description: str    # 问题描述
    suggestion: str     # 怎么改
    evidence: str       # 原文片段


@dataclass
class CritiqueResult:
    summary: str
    issues: List[CritiqueIssue]
    revised_title: str
    revised_body: str
    char_count: int = 0
    raw_response: str = ""
    # "stop" | "length" — length 表示被 max_tokens 截断
    finish_reason: str = "stop"


class ContinueEngine:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    # ---- 规划讨论 ----

    def plan_draft(self, req: ContinueRequest) -> PlanningTurn:
        """一键生成规划初稿（C 动线入口专用）。

        与 plan_turn 的关键区别：
        - plan_draft → 直接输出 5 维规划初稿（硬性 ≤200 字）
        - plan_turn  → 聊天模式，给简短建议（≤300 字）
        """
        system_prompt = self._draft_system(req)
        user_prompt = (
            f"请为《{req.book_title}》{req.next_chapter_hint}起草一份极简规划初稿，"
            f"覆盖五个维度：剧情走向 / 关键场景 / 爽点 / 节奏 / 坑点。"
            f"总字数不超过 {PLAN_DRAFT_MAX_CHARS} 字，每个维度一两句短语即可。"
        )
        messages = [
            LLMMessage("system", system_prompt),
            LLMMessage("user", user_prompt),
        ]
        # 200 字正文 + 推理模型 reasoning buffer
        resp = self.llm.chat(messages, temperature=0.7, max_tokens=600)
        content = self._truncate_plan_draft((resp.content or "").strip())
        return PlanningTurn(role="assistant", content=content)

    def plan_turn(self, req: ContinueRequest, user_message: str) -> PlanningTurn:
        """与用户讨论下一章规划。"""
        history_msgs = self._history_to_messages(req.planning_history)
        history_msgs.append(LLMMessage("user", user_message))

        system_prompt = self._planning_system(req)
        messages = [LLMMessage("system", system_prompt), *history_msgs]

        # 推理模型（如 GLM-5.2）的 reasoning_content 会吃掉 token 配额；
        # 给到 4x 留 buffer，避免正文被截断
        resp = self.llm.chat(messages, temperature=0.7, max_tokens=2400)
        return PlanningTurn(role="assistant", content=(resp.content or "").strip())

    def plan_revise(
        self,
        req: ContinueRequest,
        current_plan: str,
        user_feedback: str,
    ) -> PlanningTurn:
        """根据用户反馈**重写**规划（C 动线的"让 AI 改写"按钮专用）。

        与 plan_turn 的关键区别：
        - plan_turn  → 聊天模式，AI 给建议，用户手动合并
        - plan_revise → 重写模式，AI **直接返回完整新一版规划文本**

        内部会把"上一版规划 + 用户的反馈"一起作为上下文，让 LLM 给出修订版。
        """
        history_msgs = self._history_to_messages(req.planning_history)
        # 把"上一版规划 + 反馈"打包成单条 user 消息，AI 输出"新版规划"作为 assistant
        revision_prompt = (
            f"【上一版规划】\n{current_plan.strip() or '（空）'}\n\n"
            f"【作者的修改意见】\n{user_feedback.strip()}\n\n"
            f"请直接输出新一版的完整规划（覆盖上一版），不要再给建议、不要寒暄。"
        )
        history_msgs.append(LLMMessage("user", revision_prompt))

        system_prompt = self._revise_system(req)
        messages = [LLMMessage("system", system_prompt), *history_msgs]

        # max_tokens 给到 2400：规划文本通常 500~1500 字，留 buffer
        resp = self.llm.chat(messages, temperature=0.7, max_tokens=2400)
        return PlanningTurn(role="assistant", content=(resp.content or "").strip())

    # ---- 一键续写 ----

    # max_tokens 估算：中文 1 字 ≈ 1 token；按浮动上限 × ratio 给推理链留余量
    GENERATE_TOKEN_RATIO = 2.0
    GENERATE_EXTRA_TOKENS = 300  # 标题 / 格式
    GENERATE_MAX_TOKENS = 16000

    def generate(self, req: ContinueRequest) -> ContinueResult:
        # 按动线组装 prompt：
        # - AUTO: 不注入规划，让 AI 基于上下文和风格即兴
        # - USER_PLAN / AI_PLAN: 注入最终规划 + 强调「严格按规划写，不擅自发散」
        system_prompt = self._generation_system(req)
        user_prompt = self._generation_user(req)
        char_limit = self._char_limit(req.target_chars)
        max_tokens = self._compute_generate_max_tokens(req.target_chars)

        title = req.next_chapter_hint  # fallback；第一次解析后会覆盖
        body_parts: list[str] = []  # 累加正文片段，标题在第一次时剥离
        merged_finish = "stop"
        last_chunk_tail = ""  # 用于续写时让模型"接着写"
        max_continuations = 2  # 最多续写 2 次，防失控

        for attempt in range(max_continuations + 1):
            if attempt == 0:
                messages = [
                    LLMMessage("system", system_prompt),
                    LLMMessage("user", user_prompt),
                ]
            else:
                # 续写：把已生成的 body 作为 assistant 消息，再请"继续"
                tail_hint = last_chunk_tail[-30:] if last_chunk_tail else ""
                cont_user = (
                    f"上一段输出在「{tail_hint}」处被截断。"
                    f"请直接接续上文继续写，不要重复、不要总结、不要换行开头。"
                )
                messages = [
                    LLMMessage("system", system_prompt),
                    LLMMessage("user", user_prompt),
                    LLMMessage("assistant", "\n".join(body_parts)),
                    LLMMessage("user", cont_user),
                ]

            if attempt > 0:
                body_so_far = "\n".join(p for p in body_parts if p).strip()
                remaining = char_limit - len(body_so_far)
                if remaining <= 0:
                    break
                max_tokens = self._compute_generate_max_tokens(remaining)

            resp = self.llm.chat(
                messages,
                temperature=0.85,
                max_tokens=max_tokens,
            )
            chunk = (resp.content or "").strip()
            merged_finish = resp.finish_reason or "stop"
            last_chunk_tail = chunk

            if not chunk:
                break  # 防御：空内容就不续了

            if attempt == 0:
                # 第一次：解析标题 + 正文
                t, body0 = self._split_title_body(chunk, fallback=req.next_chapter_hint)
                title = t
                if body0:
                    body_parts.append(body0)
            else:
                # 续写追加：整段都是正文
                body_parts.append(chunk)

            if merged_finish != "length":
                break  # 自然结束

            body_so_far = "\n".join(p for p in body_parts if p).strip()
            if len(body_so_far) >= char_limit:
                log.info(
                    "正文已达字数上限 %d（目标 %d），停止自动续写",
                    char_limit,
                    req.target_chars,
                )
                break

        body = "\n".join(p for p in body_parts if p).strip()
        body = self._truncate_body(body, char_limit)
        # 保留 raw_response 方便 debug
        raw = (title + "\n\n" + body).strip()
        return ContinueResult(
            chapter_title=title,
            body=body,
            char_count=len(body),
            raw_response=raw,
            finish_reason=merged_finish,
        )

    @staticmethod
    def _char_limit(target_chars: int) -> int:
        """正文允许的最大字数（含标点），PRD F11：目标 ±30%。"""
        return max(1, int(target_chars * GENERATE_CHAR_FLOAT_RATIO))

    def _compute_generate_max_tokens(self, target_chars: int) -> int:
        """根据目标字数算 max_tokens。中文 1 字 ≈ 1 token；按浮动上限 × ratio 留 buffer。"""
        char_cap = self._char_limit(target_chars)
        est = int(char_cap * self.GENERATE_TOKEN_RATIO) + self.GENERATE_EXTRA_TOKENS
        return min(self.GENERATE_MAX_TOKENS, est)

    @staticmethod
    def _truncate_body(body: str, max_chars: int) -> str:
        """正文超限时在句/段边界截断（服务端兜底）。"""
        body = body.strip()
        if len(body) <= max_chars:
            return body
        truncated = body[:max_chars]
        min_cut = int(max_chars * 0.7)
        for sep in ("。", "！", "？", "…", "\n\n", "\n", "，"):
            idx = truncated.rfind(sep)
            if idx >= min_cut:
                return truncated[: idx + len(sep)].strip()
        log.warning("正文超长（%d > %d 字），已在硬截断", len(body), max_chars)
        return truncated.rstrip()

    # ---- AI 重写：给修改意见 + 建议重写版 ----

    def critique(
        self,
        req: ContinueRequest,
        current_draft: str,
        current_title: str = "",
    ) -> CritiqueResult:
        """对已生成的草稿做审稿 + 改写。

        两阶段：
        1) chat_json 拿结构化的修改意见（summary + issues[]）
        2) 再调一次 chat 拿改写版正文（保持原作风格，聚焦修复 issues）
        """
        if not current_draft.strip():
            raise ValueError("current_draft 不能为空：先生成草稿再请求 AI 重写。")

        # 阶段 1：修改意见（结构化 JSON）
        critique_system = self._critique_system(req, current_title=current_title)
        critique_user = self._critique_user(req, current_draft=current_draft, current_title=current_title)
        try:
            data = self.llm.chat_json(
                [LLMMessage("system", critique_system), LLMMessage("user", critique_user)],
                temperature=0.4,
                max_tokens=1800,
            )
        except Exception as e:
            log.warning("critique JSON 解析失败，回退到宽松解析: %s", e)
            raw = self.llm.chat(
                [LLMMessage("system", critique_system), LLMMessage("user", critique_user)],
                temperature=0.4,
                max_tokens=1800,
            ).content
            data = self._loose_parse_critique(raw)

        issues = [
            CritiqueIssue(
                category=str(i.get("category", "other")).lower(),
                severity=str(i.get("severity", "medium")).lower(),
                description=str(i.get("description", "")).strip(),
                suggestion=str(i.get("suggestion", "")).strip(),
                evidence=str(i.get("evidence", "")).strip(),
            )
            for i in (data.get("issues") or [])
        ]
        summary = str(data.get("summary", "")).strip() or "（AI 未给出总评）"

        # 阶段 2：重写版正文
        revise_system = self._critique_revise_system(req, current_title=current_title)
        revise_user = self._critique_revise_user(
            req, current_draft=current_draft, current_title=current_title, issues=issues
        )
        # 重写版用和 generate 一样的 token 估算
        max_tokens = self._compute_generate_max_tokens(req.target_chars)
        resp = self.llm.chat(
            [LLMMessage("system", revise_system), LLMMessage("user", revise_user)],
            temperature=0.85,
            max_tokens=max_tokens,
        )
        revised_text = (resp.content or "").strip()
        revised_title, revised_body = self._split_title_body(
            revised_text, fallback=current_title or req.next_chapter_hint
        )
        revised_body = self._truncate_body(revised_body, self._char_limit(req.target_chars))

        return CritiqueResult(
            summary=summary,
            issues=issues,
            revised_title=revised_title,
            revised_body=revised_body,
            char_count=len(revised_body),
            raw_response=revised_text,
            finish_reason=resp.finish_reason or "stop",
        )

    # ---- prompts ----

    def _draft_system(self, req: ContinueRequest) -> str:
        """plan_draft 用的 system prompt：直接输出极简规划初稿。"""
        ctx_text = req.context.render_for_prompt() if req.context else "（暂无上下文）"
        style_text = StyleProfiler._render_profile(req.style) if req.style else ""
        return (
            f"你是资深网文策划编辑，正在为《{req.book_title}》{req.next_chapter_hint}起草规划初稿。\n"
            f"请直接输出极简规划，覆盖五个维度：剧情走向 / 关键场景 / 爽点 / 节奏 / 坑点。\n\n"
            f"硬性要求：\n"
            f"1. 直接输出规划文本，不要寒暄、不要给选项、不要问作者意见。\n"
            f"2. **总长度不超过 {PLAN_DRAFT_MAX_CHARS} 字（含标点）**；五个维度各用 1~2 句短语概括，禁止长篇展开。\n"
            f"3. 用 Markdown 小标题或「维度：要点」格式，务必极简。\n"
            f"4. 必须承接最近剧情上下文，章末留钩子。\n"
            f"5. 符合原作风格与节奏。\n\n"
            f"{ctx_text}\n\n"
            f"{style_text}"
        )

    @staticmethod
    def _truncate_plan_draft(text: str, max_chars: int = PLAN_DRAFT_MAX_CHARS) -> str:
        """服务端硬性截断：LLM 超长时兜底，保证初稿不超过字数上限。"""
        text = text.strip()
        if len(text) <= max_chars:
            return text
        truncated = text[:max_chars].rstrip()
        log.warning("plan_draft 输出超长（%d 字），已截断至 %d 字", len(text), max_chars)
        return truncated

    def _planning_system(self, req: ContinueRequest) -> str:
        ctx_text = req.context.render_for_prompt() if req.context else "（暂无上下文）"
        style_text = StyleProfiler._render_profile(req.style) if req.style else ""
        return (
            f"你是资深网文策划编辑，正在和作者讨论《{req.book_title}》{req.next_chapter_hint}的规划。\n"
            f"请围绕：剧情走向 / 爽点设计 / 节奏安排 / 坑点 / 填坑 五个维度引导讨论。\n"
            f"回复要简洁、有启发性，能激发作者决策。一次回复不要超过 300 字。\n\n"
            f"{ctx_text}\n\n"
            f"{style_text}"
        )

    def _revise_system(self, req: ContinueRequest) -> str:
        """plan_revise 用的 system prompt：直接重写规划，不要给建议。"""
        ctx_text = req.context.render_for_prompt() if req.context else "（暂无上下文）"
        style_text = StyleProfiler._render_profile(req.style) if req.style else ""
        return (
            f"你是资深网文策划编辑，正在为《{req.book_title}》{req.next_chapter_hint}改写规划。\n"
            f"作者已经看过上一版规划并给出了修改意见，请**直接输出新一版完整规划**，"
            f"覆盖上一版的所有 5 个维度：剧情走向 / 关键场景 / 爽点 / 节奏 / 坑点。\n\n"
            f"硬性要求：\n"
            f"1. 直接输出新规划文本，不要寒暄、不要给建议、不要『修改说明』。\n"
            f"2. 保留上一版中作者没否定的好点子；只按作者反馈调整有问题的部分。\n"
            f"3. 规划长度 500~1500 字（中文），用 Markdown 或清晰的小标题分维度即可。\n"
            f"4. 不得与最近剧情上下文矛盾。\n\n"
            f"{ctx_text}\n\n"
            f"{style_text}"
        )

    def _generation_system(self, req: ContinueRequest) -> str:
        style_text = StyleProfiler._render_profile(req.style) if req.style else ""
        # 按动线生成不同的 system 指令
        if req.mode == ContinueMode.AUTO:
            mode_directive = (
                "本次为「一键续写」动线（A 动线）：作者未指定规划，"
                "请你基于上下文与风格自行起势与推进本章。"
            )
        elif req.mode == ContinueMode.USER_PLAN:
            mode_directive = (
                "本次为「用户规划续写」动线（B 动线）：作者已明确给出本章规划，"
                "你必须**严格按规划写**，不得擅自添加规划外的人物、事件、地点或设定；"
                "如确有必要偏离，需在正文中显式标注为「规划外内容」并由作者取舍。"
            )
        else:  # AI_PLAN
            mode_directive = (
                "本次为「AI 规划续写」动线（C 动线）：规划是 AI 起草、作者审阅讨论后锁定的最终纲要，"
                "你必须**严格按规划写**，逐项落实规划中的剧情/爽点/节奏/坑点/填坑要求；"
                "如确有必要偏离，需在正文中显式标注为「规划外内容」并由作者取舍。"
            )
        return (
            f"你是《{req.book_title}》的续写作者。\n"
            f"任务：续写{req.next_chapter_hint}。\n"
            f"动线指令：{mode_directive}\n"
            f"通用要求：\n"
            f"1. 严格按作者原作风格续写。\n"
            f"2. 正文控制在 {req.target_chars} 字左右，**不得超过 {self._char_limit(req.target_chars)} 字**；"
            f"宁可略短也不要超字数，在自然断点收笔。\n"
            f"3. 不得与已发生剧情矛盾。\n"
            f"4. 输出格式：第一行是章节标题（与前文风格一致，如『第X章 标题』），从第二行开始是正文。\n"
            f"5. 不要写总结、不要写元评论、不要『全文完』。\n\n"
            f"{style_text}"
        )

    def _generation_user(self, req: ContinueRequest) -> str:
        ctx_text = req.context.render_for_prompt() if req.context else ""
        history_text = "\n\n".join(f"{t.role}：{t.content}" for t in req.planning_history[-6:])

        if req.mode == ContinueMode.AUTO:
            # A 动线：不规划，让 AI 自行起势
            plan_block = (
                "【本章规划】\n"
                "作者未指定具体规划（A 动线·一键续写）。请基于「最近剧情上下文」，"
                "自然承接上一章末尾的钩子/悬念，保持原作节奏与风格，自行起势与推进本章。\n"
                "注意：\n"
                "1. 不要复读上一章结尾。\n"
                "2. 至少包含一个明确的事件或转折，避免流水账。\n"
                "3. 章末留一个小钩子，方便下一章续写。"
            )
            history_block = f"【规划讨论纪要】\n{history_text or '（无 — A 动线未进入规划讨论）'}"
        else:
            # B / C 动线：必须有 final_plan，否则 prompt 显式提示缺失（API 校验会先拦）
            plan_source = "作者直接拟定" if req.mode == ContinueMode.USER_PLAN else "AI 起草并经作者审阅讨论后锁定"
            plan_block = (
                f"【最终规划（来源：{plan_source}）】\n"
                f"{req.final_plan.strip() or '⚠️ 规划为空（API 校验应已拦截，请检查请求）'}"
            )
            history_block = f"【规划讨论纪要】\n{history_text or '（无）'}"

        return (
            f"【最近剧情上下文（按远→近顺序）】\n{ctx_text}\n\n"
            f"{history_block}\n\n"
            f"{plan_block}\n\n"
            f"【字数要求】正文约 {req.target_chars} 字，上限 {self._char_limit(req.target_chars)} 字，"
            f"不要超过上限。\n\n"
            f"请开始续写。"
        )

    def _critique_system(self, req: ContinueRequest, current_title: str) -> str:
        style_text = StyleProfiler._render_profile(req.style) if req.style else ""
        return (
            f"你是《{req.book_title}》的资深网文主编，正在对{req.next_chapter_hint}的 AI 草稿做审稿。\n"
            f"任务：找出草稿中所有可以改进的地方（剧情/人物/文笔/节奏/AI 味/与前文一致性等），"
            f"并给出具体可执行的修改建议。\n"
            f"语气直接但友善，针对中文网文读者口味。\n\n"
            f"你必须以 JSON 返回，结构：\n"
            f"{{\n"
            f'  "summary": "一句话总评",\n'
            f'  "issues": [\n'
            f'    {{\n'
            f'      "category": "plot|character|prose|pacing|ai_smell|consistency|other",\n'
            f'      "severity": "high|medium|low",\n'
            f'      "description": "问题描述",\n'
            f'      "suggestion": "具体怎么改",\n'
            f'      "evidence": "原文片段（短句即可，没有就空字符串）"\n'
            f"    }}\n"
            f"  ]\n"
            f"}}\n"
            f"规则：\n"
            f"1. issues 至少 1 条，至多 8 条，按 severity 严重程度排序（high 在前）。\n"
            f"2. 不要复读原文章节，只指出问题。\n"
            f"3. 找不到问题时也要给 1-2 条『可打磨』的低优先级建议。\n\n"
            f"{style_text}"
        )

    def _critique_user(self, req: ContinueRequest, current_draft: str, current_title: str) -> str:
        ctx_text = req.context.render_for_prompt() if req.context else ""
        history_text = "\n\n".join(f"{t.role}：{t.content}" for t in req.planning_history[-6:])
        plan_block = (
            f"【最终规划（作者确认）】\n{req.final_plan}"
            if req.final_plan.strip()
            else "【本章规划】\n作者未指定具体规划，本章是 AI 基于上下文即兴续写的。"
        )
        return (
            f"【最近剧情上下文（按远→近顺序）】\n{ctx_text}\n\n"
            f"【规划讨论纪要】\n{history_text or '（无）'}\n\n"
            f"{plan_block}\n\n"
            f"【当前章节标题】\n{current_title or req.next_chapter_hint}\n\n"
            f"【当前草稿（待审稿）】\n{current_draft}\n\n"
            f"请以 JSON 返回修改意见。"
        )

    def _critique_revise_system(self, req: ContinueRequest, current_title: str) -> str:
        style_text = StyleProfiler._render_profile(req.style) if req.style else ""
        return (
            f"你是《{req.book_title}》的续写作者。\n"
            f"任务：在保留原作风格和章节规划精神的前提下，"
            f"对{req.next_chapter_hint}（当前标题：{current_title or req.next_chapter_hint}）的草稿做改写，"
            f"重点修复审稿中指出的所有问题。\n"
            f"要求：\n"
            f"1. 严格按作者原作风格改写，不要变成另一种味道。\n"
            f"2. 不得与已发生剧情矛盾。\n"
            f"3. 目标字数和原稿相当（±30% 浮动即可）。\n"
            f"4. 输出格式：第一行是章节标题（与原标题风格一致），从第二行开始是正文。\n"
            f"5. 不要写总结、不要写元评论、不要『全文完』、不要写『修改说明』。\n\n"
            f"{style_text}"
        )

    def _critique_revise_user(
        self,
        req: ContinueRequest,
        current_draft: str,
        current_title: str,
        issues: List[CritiqueIssue],
    ) -> str:
        ctx_text = req.context.render_for_prompt() if req.context else ""
        issues_text = "\n".join(
            f"- [{i.severity.upper()}][{i.category}] {i.description} → {i.suggestion}"
            for i in issues
        ) or "（无具体问题）"
        # 改写时也尊重原动线：B / C 动线必须按规划改写
        if req.mode == ContinueMode.AUTO:
            plan_block = f"【本章规划】\n（无 — A 动线）"
            mode_note = "A 动线·一键续写"
        else:
            plan_source = "作者直接拟定" if req.mode == ContinueMode.USER_PLAN else "AI 起草并经作者审阅讨论后锁定"
            plan_block = f"【最终规划（来源：{plan_source}）】\n{req.final_plan or '（无）'}"
            mode_note = f"{'B 动线·用户规划续写' if req.mode == ContinueMode.USER_PLAN else 'C 动线·AI 规划续写'}"
        return (
            f"【动线】{mode_note}\n\n"
            f"【最近剧情上下文（按远→近顺序）】\n{ctx_text}\n\n"
            f"{plan_block}\n\n"
            f"【当前章节标题】\n{current_title or req.next_chapter_hint}\n\n"
            f"【当前草稿（需要改写）】\n{current_draft}\n\n"
            f"【需要修复的问题】\n{issues_text}\n\n"
            f"请输出改写后的章节（第一行标题，从第二行开始正文）。"
        )

    def _loose_parse_critique(self, raw: str) -> Dict[str, Any]:
        """宽松解析：从文本中抠出 JSON 块。"""
        text = raw.strip()
        # 去掉 markdown 代码块
        if text.startswith("```"):
            lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except Exception:
            return {"summary": "（AI 返回无法解析为 JSON）", "issues": []}

    def _history_to_messages(self, history: List[PlanningTurn]) -> List[LLMMessage]:
        return [LLMMessage(role=t.role, content=t.content) for t in history]

    def _split_title_body(self, text: str, fallback: str) -> tuple[str, str]:
        lines = text.splitlines()
        title = fallback
        body_start = 0
        for i, line in enumerate(lines[:3]):
            s = line.strip()
            if not s:
                continue
            # 第一行非空且较短，作为标题
            if i == 0 and len(s) <= 40:
                title = s
                body_start = 1
                break
        body = "\n".join(lines[body_start:]).strip()
        return title, body
