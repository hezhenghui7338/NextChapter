"""摘要生成。

对齐 Lumina segment 策略：
- 细摘要：JSON 速读卡 → 渲染为纯文本（UI 仍用 text 字段）
- 滚动上下文：前章 fine 摘要最多 1600 字
- 正文截断：4000 字（cloud chunk target）
- coarse/ultra 仍从 fine 派生，省 token
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from ..chunker import Chapter
from ..config import (
    CHAPTER_TEXT_MAX_CHARS,
    SUMMARY_CONCURRENCY,
    SUMMARY_CONTEXT_MAX_CHARS,
    SUMMARY_CONTEXT_QUERY_LIMIT,
    SUMMARY_DERIVED_MAX_TOKENS,
    SUMMARY_FINE_MAX_TOKENS,
    SUMMARY_LLM_MAX_RETRIES,
    SUMMARY_SEGMENT_TIMEOUT_SECONDS,
)
from ..llm import LLMClient, LLMError, LLMMessage
from .prompts import CHAPTER_JSON_PROMPT, CONTEXT_GUIDANCE, JSON_RETRY_SUFFIX

log = logging.getLogger("nextchapter.summarize")


class SummaryTier(str, Enum):
    FINE = "fine"      # 400 字
    COARSE = "coarse"  # 150 字
    ULTRA = "ultra"    # 60 字


@dataclass
class ChapterSummary:
    chapter_index: int
    title: str
    tier: SummaryTier
    text: str
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.text)


def build_chapter_context(prior_fine: List[ChapterSummary]) -> str:
    """拼接前章 fine 摘要作为背景（对齐 Lumina build_summary_context）。"""
    if not prior_fine:
        return ""
    parts: list[str] = []
    total = 0
    for s in prior_fine[-SUMMARY_CONTEXT_QUERY_LIMIT:]:
        chunk = f"{s.title}：{s.text.strip()}"
        if total + len(chunk) > SUMMARY_CONTEXT_MAX_CHARS:
            remain = SUMMARY_CONTEXT_MAX_CHARS - total
            if remain <= 20:
                break
            chunk = chunk[:remain] + "…"
        parts.append(chunk)
        total += len(chunk)
        if total >= SUMMARY_CONTEXT_MAX_CHARS:
            break
    if not parts:
        return ""
    return CONTEXT_GUIDANCE.format(context="\n".join(parts))


def _coerce_str_list(value) -> list[str]:
    """LLM 有时把 sentences 写成字符串；直接迭代 str 会变成逐字分行。"""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def render_summary_card(data: dict) -> str:
    """JSON 速读卡 → 纯文本（供 UI / 滑动窗口使用）。"""
    lines: list[str] = []
    for text in _coerce_str_list(data.get("sentences")):
        lines.append(text)
    bullets = data.get("bullets") or []
    if isinstance(bullets, dict):
        bullets = [bullets]
    elif not isinstance(bullets, list):
        bullets = []
    for item in bullets:
        if isinstance(item, dict):
            label = str(item.get("label") or "").strip()
            body = str(item.get("body") or "").strip()
            if label and body:
                lines.append(f"· {label}：{body}")
            elif body:
                lines.append(f"· {body}")
        elif item:
            lines.append(f"· {str(item).strip()}")
    rendered = "\n".join(lines).strip()
    if not rendered:
        raise ValueError("JSON 摘要为空")
    return rendered


def parse_summary_json(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = "\n".join(l for l in s.splitlines() if not l.strip().startswith("```"))
    data = json.loads(s)
    if not isinstance(data, dict):
        raise ValueError("摘要 JSON 必须是对象")
    return data


class Summarizer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def summarize(
        self,
        chapter: Chapter,
        tier: SummaryTier,
        *,
        prior_fine: Optional[List[ChapterSummary]] = None,
    ) -> ChapterSummary:
        if tier == SummaryTier.FINE:
            return self._summarize_fine(chapter, prior_fine or [])
        prompts = {
            SummaryTier.COARSE: self._prompt_coarse(chapter),
            SummaryTier.ULTRA: self._prompt_ultra(chapter),
        }
        msg = prompts[tier]
        resp = self._chat_summarize([msg], max_tokens=SUMMARY_DERIVED_MAX_TOKENS)
        return ChapterSummary(
            chapter_index=chapter.index,
            title=chapter.title,
            tier=tier,
            text=resp.content.strip(),
        )

    def summarize_from_summary(
        self, fine: ChapterSummary, tier: SummaryTier
    ) -> ChapterSummary:
        """从 fine 摘要派生 coarse/ultra（避免再读原文，省 token）。"""
        if fine.tier != SummaryTier.FINE:
            raise ValueError("summarize_from_summary 需要 FINE 档摘要作为输入")
        msg = self._prompt_from_summary(fine.text, tier)
        resp = self._chat_summarize([msg], max_tokens=SUMMARY_DERIVED_MAX_TOKENS)
        return ChapterSummary(
            chapter_index=fine.chapter_index,
            title=fine.title,
            tier=tier,
            text=resp.content.strip(),
        )

    def summarize_chapter_tiers(
        self,
        chapter: Chapter,
        prior_fine: Optional[List[ChapterSummary]] = None,
    ) -> List[ChapterSummary]:
        """单章三档：fine → coarse/ultra 派生。"""
        fine = self._summarize_fine(chapter, prior_fine or [])
        return [
            fine,
            self.summarize_from_summary(fine, SummaryTier.COARSE),
            self.summarize_from_summary(fine, SummaryTier.ULTRA),
        ]

    def summarize_all(self, chapters: List[Chapter], tier: SummaryTier) -> List[ChapterSummary]:
        results: List[ChapterSummary] = []
        prior_fine: List[ChapterSummary] = []
        for ch in chapters:
            log.info("summarizing chapter %d (%s) at %s tier", ch.index, ch.title, tier.value)
            if tier == SummaryTier.FINE:
                s = self._summarize_fine(ch, prior_fine)
                prior_fine.append(s)
            else:
                s = self.summarize(ch, tier)
            results.append(s)
        return results

    def summarize_all_tiers(
        self,
        chapters: List[Chapter],
        *,
        prior_fine: Optional[List[ChapterSummary]] = None,
        concurrency: Optional[int] = None,
    ) -> List[ChapterSummary]:
        workers = max(1, concurrency if concurrency is not None else SUMMARY_CONCURRENCY)
        prior: List[ChapterSummary] = list(prior_fine or [])
        out: List[ChapterSummary] = []

        for wave_start in range(0, len(chapters), workers):
            wave = chapters[wave_start : wave_start + workers]
            prior_snapshot = list(prior)
            log.info(
                "summarizing chapters %s (wave %d, concurrency=%d)",
                [ch.index for ch in wave],
                wave_start // workers + 1,
                workers,
            )

            if workers == 1 or len(wave) == 1:
                for ch in wave:
                    batch = self.summarize_chapter_tiers(ch, prior_snapshot)
                    out.extend(batch)
                    prior.append(batch[0])
                continue

            wave_results: List[tuple[int, List[ChapterSummary]]] = []
            with ThreadPoolExecutor(max_workers=len(wave)) as pool:
                future_map = {
                    pool.submit(self.summarize_chapter_tiers, ch, prior_snapshot): ch
                    for ch in wave
                }
                for future in as_completed(future_map):
                    ch = future_map[future]
                    wave_results.append((ch.index, future.result()))

            for _, batch in sorted(wave_results, key=lambda item: item[0]):
                out.extend(batch)
                prior.append(batch[0])

        return out

    # ---- internals ----

    def _chat_summarize(
        self,
        messages: List[LLMMessage],
        *,
        max_tokens: int,
        response_format: Optional[str] = None,
    ):
        return self.llm.chat(
            messages,
            temperature=0.3,
            max_tokens=max_tokens,
            timeout=SUMMARY_SEGMENT_TIMEOUT_SECONDS,
            response_format=response_format,
        )

    def _summarize_fine_plain(self, ch: Chapter, prior_fine: List[ChapterSummary]) -> ChapterSummary:
        """JSON 失败时的纯文本回退（兼容 Flash/思考模型）。"""
        context_block = build_chapter_context(prior_fine)
        body = ch.body[:CHAPTER_TEXT_MAX_CHARS]
        prompt = (
            f"{context_block}"
            f"请为下面这章中文网文生成 400 字左右的细摘要，覆盖：核心事件、人物、悬念。\n\n"
            f"【章节】{ch.title}\n【正文】\n{body}\n\n"
            f"直接输出摘要正文，不要用『本章讲述了』开头，不要输出 JSON。"
        )
        resp = self._chat_summarize([LLMMessage("user", prompt)], max_tokens=SUMMARY_FINE_MAX_TOKENS)
        text = resp.content.strip()
        if not text:
            raise LLMError(f"章节「{ch.title}」纯文本摘要仍为空")
        return ChapterSummary(
            chapter_index=ch.index,
            title=ch.title,
            tier=SummaryTier.FINE,
            text=text,
        )

    def _summarize_fine(self, ch: Chapter, prior_fine: List[ChapterSummary]) -> ChapterSummary:
        context_block = build_chapter_context(prior_fine)
        body = ch.body[:CHAPTER_TEXT_MAX_CHARS]
        base_prompt = CHAPTER_JSON_PROMPT.format(
            context_block=context_block,
            title=ch.title,
            text=body,
        )
        last_err: Exception | None = None
        prompt = base_prompt
        for attempt in range(1, SUMMARY_LLM_MAX_RETRIES + 1):
            try:
                if attempt >= SUMMARY_LLM_MAX_RETRIES:
                    return self._summarize_fine_plain(ch, prior_fine)
                resp = self._chat_summarize(
                    [LLMMessage("user", prompt)],
                    max_tokens=SUMMARY_FINE_MAX_TOKENS,
                    response_format="json" if attempt >= 2 else None,
                )
                data = parse_summary_json(resp.content)
                text = render_summary_card(data)
                return ChapterSummary(
                    chapter_index=ch.index,
                    title=ch.title,
                    tier=SummaryTier.FINE,
                    text=text,
                )
            except (LLMError, json.JSONDecodeError, ValueError) as e:
                last_err = e
                log.warning(
                    "fine summary attempt %s/%s failed for ch %s: %s",
                    attempt, SUMMARY_LLM_MAX_RETRIES, ch.index, e,
                )
                prompt = base_prompt + JSON_RETRY_SUFFIX
        raise LLMError(f"章节「{ch.title}」细摘要失败（{SUMMARY_LLM_MAX_RETRIES} 次）：{last_err}")

    def _prompt_coarse(self, ch: Chapter) -> LLMMessage:
        return LLMMessage(
            "user",
            f"把下面这章压缩成 150 字左右的中文剧情摘要，保留：核心冲突、关键人物、主要转折、伏笔触发。\n\n"
            f"【章节】{ch.title}\n【正文】\n{ch.body[:CHAPTER_TEXT_MAX_CHARS]}\n\n"
            f"直接输出。",
        )

    def _prompt_ultra(self, ch: Chapter) -> LLMMessage:
        return LLMMessage(
            "user",
            f"把下面这章浓缩成 60 字以内的一句话摘要，只保留最核心的剧情推进。\n\n"
            f"【章节】{ch.title}\n【正文】\n{ch.body[:CHAPTER_TEXT_MAX_CHARS]}\n",
        )

    def _prompt_from_summary(self, fine_text: str, tier: SummaryTier) -> LLMMessage:
        if tier == SummaryTier.COARSE:
            return LLMMessage(
                "user",
                f"下面是章节的细摘要（约 400 字）。请压缩到 150 字左右，保留：核心冲突、关键人物、主要转折、伏笔触发。\n\n"
                f"{fine_text}\n\n"
                f"直接输出。",
            )
        return LLMMessage(
            "user",
            f"下面是章节的细摘要。请浓缩成 60 字以内的一句话，只保留最核心的剧情推进。\n\n"
            f"{fine_text}\n\n"
            f"直接输出。",
        )
