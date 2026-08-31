"""摘要生成。

三种档位：
- fine: 400 字左右，覆盖人物/事件/地点
- coarse: 150 字左右，核心剧情 + 关键转折
- ultra: 60 字左右，浓缩成一句话
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List

from ..chunker import Chapter
from ..llm import LLMClient, LLMMessage

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


class Summarizer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def summarize(self, chapter: Chapter, tier: SummaryTier) -> ChapterSummary:
        prompts = {
            SummaryTier.FINE: self._prompt_fine(chapter),
            SummaryTier.COARSE: self._prompt_coarse(chapter),
            SummaryTier.ULTRA: self._prompt_ultra(chapter),
        }
        msg = prompts[tier]
        resp = self.llm.chat([msg], temperature=0.3)
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
        resp = self.llm.chat([msg], temperature=0.3, max_tokens=400)
        return ChapterSummary(
            chapter_index=fine.chapter_index,
            title=fine.title,
            tier=tier,
            text=resp.content.strip(),
        )

    def summarize_all(self, chapters: List[Chapter], tier: SummaryTier) -> List[ChapterSummary]:
        results: List[ChapterSummary] = []
        for ch in chapters:
            log.info("summarizing chapter %d (%s) at %s tier", ch.index, ch.title, tier.value)
            results.append(self.summarize(ch, tier))
        return results

    def summarize_all_tiers(
        self, chapters: List[Chapter]
    ) -> List[ChapterSummary]:
        """一次性生成三档摘要。

        流程：
        1) 全部章节生成 fine（基于原文）
        2) 全部章节生成 coarse（基于 fine 摘要，省 token）
        3) 全部章节生成 ultra（基于 fine 摘要，省 token）
        """
        fine_list = self.summarize_all(chapters, SummaryTier.FINE)
        out: List[ChapterSummary] = list(fine_list)
        for fine in fine_list:
            out.append(self.summarize_from_summary(fine, SummaryTier.COARSE))
            out.append(self.summarize_from_summary(fine, SummaryTier.ULTRA))
        return out

    # ---- prompts ----

    def _prompt_fine(self, ch: Chapter) -> LLMMessage:
        return LLMMessage(
            "user",
            f"请为下面这章中文网文生成 400 字左右的细摘要，要求覆盖：核心事件、主要人物动作与心理、关键对话要点、重要设定揭示、未解决的悬念。\n\n"
            f"【章节】{ch.title}\n【正文】\n{ch.body[:6000]}\n\n"
            f"直接输出摘要，不要用『本章讲述了』开头。",
        )

    def _prompt_coarse(self, ch: Chapter) -> LLMMessage:
        return LLMMessage(
            "user",
            f"把下面这章压缩成 150 字左右的中文剧情摘要，保留：核心冲突、关键人物、主要转折、伏笔触发。\n\n"
            f"【章节】{ch.title}\n【正文】\n{ch.body[:6000]}\n\n"
            f"直接输出。",
        )

    def _prompt_ultra(self, ch: Chapter) -> LLMMessage:
        return LLMMessage(
            "user",
            f"把下面这章浓缩成 60 字以内的一句话摘要，只保留最核心的剧情推进。\n\n"
            f"【章节】{ch.title}\n【正文】\n{ch.body[:6000]}\n",
        )

    def _prompt_from_summary(self, fine_text: str, tier: SummaryTier) -> LLMMessage:
        """从已生成的细摘要派生粗/极简摘要（省 token）。"""
        if tier == SummaryTier.COARSE:
            return LLMMessage(
                "user",
                f"下面是章节的细摘要（约 400 字）。请压缩到 150 字左右，保留：核心冲突、关键人物、主要转折、伏笔触发。\n\n"
                f"{fine_text}\n\n"
                f"直接输出。",
            )
        # ULTRA
        return LLMMessage(
            "user",
            f"下面是章节的细摘要。请浓缩成 60 字以内的一句话，只保留最核心的剧情推进。\n\n"
            f"{fine_text}\n\n"
            f"直接输出。",
        )
