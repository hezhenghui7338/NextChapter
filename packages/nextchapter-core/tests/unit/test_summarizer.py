"""摘要器测试。覆盖 PRD F3/F4/F5：三档摘要。"""
import pytest

from nextchapter_core.chunker import Chapter
from nextchapter_core.summarize import Summarizer, SummaryTier
from nextchapter_core.summarize.summarizer import render_summary_card
from tests.support.mock_llm import MockLLMClient

pytestmark = pytest.mark.unit


def make_chapter(idx: int, body_len: int = 200) -> Chapter:
    body = "这是章节正文。" * (body_len // 6)
    return Chapter(index=idx, title=f"第{idx+1}章 X", body=body, kind="chapter")


def test_render_summary_card_sentences_as_string():
    """LLM 返回 sentences 字符串时不应逐字分行。"""
    text = render_summary_card({
        "sentences": "主角李青云在洛阳遇见老者，获得剑谱。",
        "bullets": [{"label": "转折", "body": "老者身份成谜。"}],
    })
    assert "李青云" in text
    assert "\n主\n" not in text
    assert text.startswith("主角李青云")


def test_summarize_fine_uses_correct_prompt():
    llm = MockLLMClient()
    llm.queue_response(
        '{"sentences":["概述"],"bullets":[{"label":"事件","body":"主角李青云在洛阳遇见老者，获得剑谱。"},{"label":"转折","body":"x"},{"label":"悬念","body":"y"}]}'
    )
    summarizer = Summarizer(llm)
    ch = make_chapter(0)
    s = summarizer.summarize(ch, SummaryTier.FINE)
    assert s.chapter_index == 0
    assert s.tier == SummaryTier.FINE
    assert "李青云" in s.text or "概述" in s.text
    last_call = llm.calls[-1]
    assert "第1章" in last_call["messages"][0]["content"]
    assert "JSON" in last_call["messages"][0]["content"]


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
    json_fine = '{"sentences":["s"],"bullets":[{"label":"a","body":"b"},{"label":"c","body":"d"},{"label":"e","body":"f"}]}'
    llm.queue_response(json_fine).queue_response(json_fine).queue_response(json_fine)
    llm.queue_response("coarse1").queue_response("ultra1")
    llm.queue_response("coarse2").queue_response("ultra2")
    llm.queue_response("coarse3").queue_response("ultra3")
    summarizer = Summarizer(llm)
    chapters = [make_chapter(i) for i in range(3)]
    summaries = summarizer.summarize_all(chapters, SummaryTier.FINE)
    assert len(summaries) == 3
    assert [s.chapter_index for s in summaries] == [0, 1, 2]
    assert llm.call_count == 3


def test_summarizer_plain_text_fallback():
    llm = MockLLMClient()
    llm.set_callback(lambda m, kw: (
        "纯文本摘要：主角经历波折，最终破局，留下新的悬念。"
        if "不要输出 JSON" in m[0].content
        else ""
    ))
    summarizer = Summarizer(llm)
    s = summarizer.summarize(make_chapter(0), SummaryTier.FINE)
    assert "纯文本摘要" in s.text
