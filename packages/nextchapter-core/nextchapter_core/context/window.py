"""滑动窗口 + 分级压缩。

按用户决策：最近 5 章细摘要 + 中间 10 章粗摘要 + 远端 10 章极致压缩（合计 25 章）。
更早的章节不进上下文，仅在 fact-bank 留痕迹（P1）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..config import ContextSettings
from ..summarize import ChapterSummary, SummaryTier


@dataclass
class WindowedContext:
    """组装好的窗口上下文，供续写 prompt 注入。"""

    fine: List[ChapterSummary]      # 最近 N 章细摘要
    coarse: List[ChapterSummary]    # 中间 N 章粗摘要
    ultra: List[ChapterSummary]     # 远端 N 章极致压缩
    total_chapters: int             # 整本书总章节数
    # Swift 经 /context/build 拼好后传入 API 的预渲染文本；非空时优先使用
    rendered_override: str = ""

    def render_for_prompt(self) -> str:
        """拼成可注入 prompt 的中文文本。"""
        if self.rendered_override.strip():
            return self.rendered_override.strip()
        parts: list[str] = []
        if self.ultra:
            parts.append("【远端剧情概要（每章一句话）】")
            parts.extend(f"· {s.title}：{s.text}" for s in self.ultra)
        if self.coarse:
            parts.append("\n【中期剧情摘要】")
            parts.extend(f"· {s.title}：{s.text}" for s in self.coarse)
        if self.fine:
            parts.append("\n【近期剧情细摘要】")
            parts.extend(f"· {s.title}：{s.text}" for s in self.fine)
        if self.total_chapters > len(self.fine) + len(self.coarse) + len(self.ultra):
            skipped = self.total_chapters - len(self.fine) - len(self.coarse) - len(self.ultra)
            parts.insert(0, f"（共 {self.total_chapters} 章，以下是最近 {len(self.fine) + len(self.coarse) + len(self.ultra)} 章的分级摘要；前 {skipped} 章未引入）")
        return "\n".join(parts)


class ContextWindow:
    def __init__(self, settings: ContextSettings):
        self.settings = settings

    def build(self, summaries: List[ChapterSummary]) -> WindowedContext:
        """根据 settings 的分级策略，从 summaries（按章节顺序）切出三档。

        策略：
        - 短书（n <= 窗口大小 25）：全部章节进 fine，coarse/ultra 为空。
          （短书上下文窗口装得下，没必要做分级压缩；保留全部信息。）
        - 长书（n > 25）：取最近 25 章，按 fine 5 + coarse 10 + ultra 10 切。
          （再之前的章节不进上下文，P1 用 fact-bank 留痕。）
        """
        n = len(summaries)
        if n == 0:
            return WindowedContext(fine=[], coarse=[], ultra=[], total_chapters=0)

        cfg = self.settings
        window = cfg.recent_chapter_count + cfg.middle_chapter_count + cfg.far_chapter_count  # 默认 25

        if n <= window:
            # 短书：全部 fine
            fine_n, coarse_n, ultra_n = n, 0, 0
        else:
            # 长书：最近 window 章内部分级
            fine_n = cfg.recent_chapter_count
            coarse_n = cfg.middle_chapter_count
            ultra_n = cfg.far_chapter_count

        # 从末尾往前取
        tail = list(reversed(summaries))
        fine = list(reversed(tail[:fine_n]))
        coarse = list(reversed(tail[fine_n : fine_n + coarse_n]))
        ultra = list(reversed(tail[fine_n + coarse_n : fine_n + coarse_n + ultra_n]))

        return WindowedContext(fine=fine, coarse=coarse, ultra=ultra, total_chapters=n)
