"""滑动窗口测试。覆盖 PRD F6：25 章分级窗口 + 短书降级。"""
import pytest

from nextchapter_core.config import ContextSettings
from nextchapter_core.context import ContextWindow
from nextchapter_core.summarize import ChapterSummary, SummaryTier

pytestmark = pytest.mark.unit


def make_summary(i: int) -> ChapterSummary:
    return ChapterSummary(chapter_index=i, title=f"第{i+1}章", tier=SummaryTier.FINE, text=f"summary {i}")


def test_build_default_window():
    s = ContextSettings()
    w = ContextWindow(s)
    summaries = [make_summary(i) for i in range(30)]
    wc = w.build(summaries)
    assert len(wc.fine) == s.recent_chapter_count
    assert len(wc.coarse) == s.middle_chapter_count
    assert len(wc.ultra) == s.far_chapter_count
    assert wc.total_chapters == 30
    # 验证选取的是最后 25 章
    assert wc.fine[0].chapter_index == 25
    assert wc.coarse[0].chapter_index == 15
    assert wc.ultra[0].chapter_index == 5


def test_build_short_book():
    """8 章不够填满三档，应全部进入 fine 槽。"""
    s = ContextSettings()
    w = ContextWindow(s)
    summaries = [make_summary(i) for i in range(8)]
    wc = w.build(summaries)
    # 8 章全在 fine 槽
    assert len(wc.fine) == 8
    assert len(wc.coarse) == 0
    assert len(wc.ultra) == 0
    # 验证是从最早到最新排列
    assert [s.chapter_index for s in wc.fine] == list(range(8))


def test_render_prompt():
    s = ContextSettings()
    w = ContextWindow(s)
    summaries = [make_summary(i) for i in range(30)]
    wc = w.build(summaries)
    text = wc.render_for_prompt()
    assert "远端剧情概要" in text
    assert "中期剧情摘要" in text
    assert "近期剧情细摘要" in text
    assert "前 5 章未引入" in text
