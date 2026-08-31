"""风格 profiler 测试。覆盖 PRD F7/F8：few-shot 抽取 + 反 AI 味提示词。"""
import pytest

from nextchapter_core.chunker import Chapter
from nextchapter_core.config import StyleSettings
from nextchapter_core.style import ANTI_AI_PRESETS, StyleProfiler
from tests.support.mock_llm import MockLLMClient

pytestmark = pytest.mark.unit


def make_chapters(n: int = 5) -> list[Chapter]:
    """每章 ~600 字符，足够触发 few-shot 抽取。"""
    out = []
    base = (
        "这是第X章的正文。少年踏入江湖，剑眉星目，意气风发。"
        "他身后背着一柄玄铁长剑，剑穗随风轻扬。"
        "夜宿客栈，忽闻隔壁传来打斗之声。他推门而出，恰见三名黑衣人围攻一名青衫老者。"
        "老者临终前将一本泛黄剑谱塞入他手中，嘱他务必送至峨眉山。"
        "李青云心念一动，抽剑而出加入战团。他剑法凌厉，三招两式便将一名黑衣人刺倒。"
        "剩余两人见势不妙，立刻抽身退走。临走时丢下一句狠话：此事没完，等着瞧。"
    )
    for i in range(n):
        # 重复 base 直到超过 600 字符
        body = (base * 3)[:700]
        out.append(Chapter(index=i, title=f"第{i+1}章 标题{i}", body=body, kind="chapter"))
    return out


def test_anti_ai_presets_have_three_tiers():
    assert set(ANTI_AI_PRESETS.keys()) == {"default", "strong", "mild"}
    # 强档必须包含「禁止」字样
    assert "禁止" in ANTI_AI_PRESETS["strong"]


def test_extract_few_shot_samples():
    llm = MockLLMClient()
    profiler = StyleProfiler(llm, StyleSettings(few_shot_chapters=3, anti_ai_preset="default"))
    profile = profiler.profile(make_chapters(5))
    # 应该只取前 3 章
    assert len(profile.samples) == 3
    # 样本是从章节中段取的，约 600 字符
    for s in profile.samples:
        assert 200 < len(s) < 700


def test_profile_with_empty_chapters():
    llm = MockLLMClient()
    profiler = StyleProfiler(llm, StyleSettings())
    profile = profiler.profile([])
    assert profile.samples == []
    assert profile.description == ""  # 没有样本就不调用 LLM


def test_profile_includes_anti_ai_directive():
    llm = MockLLMClient()
    profiler = StyleProfiler(llm, StyleSettings(anti_ai_preset="strong"))
    profile = profiler.profile(make_chapters(3))
    assert "禁止" in profile.anti_ai_directive


def test_render_contains_all_parts():
    llm = MockLLMClient()
    llm.queue_response("句长偏好：长短句交替；修辞：白描为主...")
    profiler = StyleProfiler(llm, StyleSettings())
    profile = profiler.profile(make_chapters(3))
    rendered = profiler.render(profile)
    # anti_ai_directive 默认档 = "写作约束："
    assert "写作约束" in rendered
    # description 来自 LLM
    assert "原作风格" in rendered
    assert "样本 1" in rendered
