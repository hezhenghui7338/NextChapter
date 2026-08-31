"""摘要器测试。覆盖 PRD F3/F4/F5：三档摘要。"""
import pytest

from nextchapter_core.chunker import Chapter
from nextchapter_core.summarize import Summarizer, SummaryTier
from tests.support.mock_llm import MockLLMClient

pytestmark = pytest.mark.unit


def make_chapter(idx: int, body_len: int = 200) -> Chapter:
    body = "这是章节正文。" * (body_len // 6)
    return Chapter(index=idx, title=f"第{idx+1}章 X", body=body, kind="chapter")


def test_summarize_fine_uses_correct_prompt():
    llm = MockLLMClient()
    llm.queue_response("主角李青云在洛阳遇见老者，获得剑谱。")
    summarizer = Summarizer(llm)
    ch = make_chapter(0)
    s = summarizer.summarize(ch, SummaryTier.FINE)
    assert s.chapter_index == 0
    assert s.tier == SummaryTier.FINE
    # LLM 收到的 prompt 应该包含「400 字左右」和章节标题
    last_call = llm.calls[-1]
    assert "第1章" in last_call["messages"][0]["content"]
    assert "400" in last_call["messages"][0]["content"]


def test_summarize_coarse_prompt_mentions_150():
    llm = MockLLMClient()
    llm.queue_response("一句话压缩。")
    summarizer = Summarizer(llm)
    summarizer.summarize(make_chapter(0), SummaryTier.COARSE)
    assert "150" in llm.calls[-1]["messages"][0]["content"]


def test_summarize_ultra_prompt_mentions_60():
    llm = MockLLMClient()
    llm.queue_response("一句话。")
    summarizer = Summarizer(llm)
    summarizer.summarize(make_chapter(0), SummaryTier.ULTRA)
    assert "60" in llm.calls[-1]["messages"][0]["content"]


def test_summarize_all_returns_list():
    llm = MockLLMClient()
    llm.queue_response("s1").queue_response("s2").queue_response("s3")
    summarizer = Summarizer(llm)
    chapters = [make_chapter(i) for i in range(3)]
    summaries = summarizer.summarize_all(chapters, SummaryTier.FINE)
    assert len(summaries) == 3
    assert [s.chapter_index for s in summaries] == [0, 1, 2]
    assert llm.call_count == 3
