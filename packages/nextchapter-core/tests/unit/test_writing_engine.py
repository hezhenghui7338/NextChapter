"""续写引擎测试。覆盖 PRD F9/F10a/F10b/F10c/F11。"""
import json

import pytest

from nextchapter_core.context import WindowedContext
from nextchapter_core.style import StyleProfile
from nextchapter_core.summarize import ChapterSummary, SummaryTier
from nextchapter_core.writing import (
    ContinueEngine,
    ContinueMode,
    ContinueRequest,
    PlanningTurn,
)
from tests.support.mock_llm import MockLLMClient

pytestmark = pytest.mark.unit


def make_summaries(n: int = 3) -> list[ChapterSummary]:
    return [ChapterSummary(chapter_index=i, title=f"第{i+1}章", tier=SummaryTier.FINE, text=f"summary {i}") for i in range(n)]


def make_ctx() -> WindowedContext:
    return WindowedContext(
        fine=make_summaries(3),
        coarse=[],
        ultra=[],
        total_chapters=3,
    )


def make_style() -> StyleProfile:
    return StyleProfile(
        samples=[],
        description="原作风格：句长中等，白描为主",
        anti_ai_directive="1. 避免排比\n2. 避免空洞抒情",
    )


def test_plan_turn_uses_history():
    llm = MockLLMClient()
    llm.queue_response("AI 回复：建议主角先探查敌情...")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试书",
        next_chapter_hint="第 4 章",
        planning_history=[
            PlanningTurn(role="user", content="第 4 章要怎么写？"),
            PlanningTurn(role="assistant", content="可以先讨论爽点。"),
        ],
        context=make_ctx(),
        style=make_style(),
    )
    turn = engine.plan_turn(req, "想写一个反杀的爽点")
    assert turn.role == "assistant"
    assert "反杀" in turn.content or "建议" in turn.content

    # LLM 应该收到 system + 2 history + 1 user = 4 条
    last = llm.calls[-1]
    msgs = last["messages"]
    assert len(msgs) == 4
    # 至少能找到 user 的「反杀」
    combined = " ".join(m["content"] for m in msgs)
    assert "反杀" in combined
    assert "测试书" in combined
    assert "第 4 章" in combined


def test_plan_draft_outputs_full_plan():
    """C 动线入口：plan_draft 应直接输出完整规划初稿。"""
    llm = MockLLMClient()
    llm.queue_response(
        "## 剧情走向\n主角与师妹对峙。\n\n## 关键场景\n藏经阁禁书。\n\n## 爽点\n身份暴露。"
    )
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试书",
        next_chapter_hint="第 4 章",
        context=make_ctx(),
        style=make_style(),
    )
    turn = engine.plan_draft(req)
    assert turn.role == "assistant"
    assert "剧情走向" in turn.content

    from nextchapter_core.writing.engine import PLAN_DRAFT_MAX_CHARS

    last = llm.calls[-1]
    system_msg = next(m for m in last["messages"] if m["role"] == "system")
    assert "起草规划初稿" in system_msg["content"]
    assert f"{PLAN_DRAFT_MAX_CHARS} 字" in system_msg["content"]
    assert "500~1500" not in system_msg["content"]


def test_plan_draft_truncates_overlong_response():
    """plan_draft 服务端硬性截断：LLM 超长时不超过 200 字。"""
    from nextchapter_core.writing.engine import PLAN_DRAFT_MAX_CHARS

    llm = MockLLMClient()
    llm.queue_response("章" * 500)
    engine = ContinueEngine(llm)
    req = ContinueRequest(book_title="测试书", next_chapter_hint="第 4 章")
    turn = engine.plan_draft(req)
    assert len(turn.content) == PLAN_DRAFT_MAX_CHARS


def test_plan_revise_rewrites_plan_from_feedback():
    """C 动线优化：plan_revise 应根据反馈重写完整规划。"""
    llm = MockLLMClient()
    llm.queue_response("## 剧情走向\n改为智取，不用硬刚。")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试书",
        next_chapter_hint="第 4 章",
        context=make_ctx(),
        style=make_style(),
    )
    turn = engine.plan_revise(req, "旧规划：硬刚反杀", "把反杀改成智取")
    assert turn.role == "assistant"
    assert "智取" in turn.content

    last = llm.calls[-1]
    user_msg = next(m for m in last["messages"] if m["role"] == "user")
    system_msg = next(m for m in last["messages"] if m["role"] == "system")
    assert "上一版规划" in user_msg["content"]
    assert "把反杀改成智取" in user_msg["content"]
    assert "改写规划" in system_msg["content"]


# ---- A 动线：mode=AUTO ----


def test_generate_auto_mode_improvises_without_plan():
    """A 动线：mode=AUTO + 空 final_plan，AI 即兴续写。覆盖 PRD F10a。"""
    llm = MockLLMClient()
    llm.queue_response("第四章 自定之局\n\n李青云推门而出，寒风扑面，街角有人影一闪。")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        target_chars=500,
        mode=ContinueMode.AUTO,
        final_plan="",
        context=make_ctx(),
        style=make_style(),
    )
    result = engine.generate(req)
    assert "第四章" in result.chapter_title
    assert "李青云" in result.body
    assert result.char_count > 0

    # prompt 应有"未指定规划 / A 动线"的提示
    last = llm.calls[-1]
    user_msg = next(m for m in last["messages"] if m["role"] == "user")
    system_msg = next(m for m in last["messages"] if m["role"] == "system")
    assert "A 动线" in system_msg["content"]
    assert "未指定" in user_msg["content"] or "即兴" in user_msg["content"]


# ---- B 动线：mode=USER_PLAN ----


def test_generate_user_plan_mode_strictly_follows_plan():
    """B 动线：mode=USER_PLAN + 用户填的规划，AI 严格按规划写。覆盖 PRD F10b。"""
    llm = MockLLMClient()
    llm.queue_response("第四章 X\n\n正文")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        target_chars=500,
        mode=ContinueMode.USER_PLAN,
        final_plan="主角反杀，三招两式",
        context=make_ctx(),
    )
    engine.generate(req)
    last = llm.calls[-1]
    user_msg = next(m for m in last["messages"] if m["role"] == "user")
    system_msg = next(m for m in last["messages"] if m["role"] == "system")
    # system 提示 B 动线 + 严格按规划
    assert "B 动线" in system_msg["content"]
    assert "严格按规划" in system_msg["content"]
    # user 透传规划原文
    assert "主角反杀" in user_msg["content"]
    assert "作者直接拟定" in user_msg["content"]


# ---- C 动线：mode=AI_PLAN ----


def test_generate_ai_plan_mode_uses_discussed_plan():
    """C 动线：mode=AI_PLAN + 讨论锁定的最终规划，AI 按规划写。覆盖 PRD F10c。"""
    llm = MockLLMClient()
    llm.queue_response("第四章 终局\n\n正文")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        target_chars=500,
        mode=ContinueMode.AI_PLAN,
        final_plan="主角最终反杀，三招两式",
        planning_history=[
            PlanningTurn(role="user", content="第 4 章要怎么写？"),
            PlanningTurn(role="assistant", content="可以走反杀路线。"),
            PlanningTurn(role="user", content="锁定：主角反杀，三招两式"),
        ],
        context=make_ctx(),
    )
    engine.generate(req)
    last = llm.calls[-1]
    user_msg = next(m for m in last["messages"] if m["role"] == "user")
    system_msg = next(m for m in last["messages"] if m["role"] == "system")
    # system 提示 C 动线 + 严格按规划
    assert "C 动线" in system_msg["content"]
    assert "严格按规划" in system_msg["content"]
    # user 透传规划原文 + 标记规划来源是 AI 起草+作者锁定
    assert "主角最终反杀" in user_msg["content"]
    assert "AI 起草" in user_msg["content"]
    # 讨论纪要也被带进去
    assert "反杀路线" in user_msg["content"]


# ---- 通用 ----


def test_generate_produces_title_and_body():
    llm = MockLLMClient()
    llm.queue_response("第四章 反杀之夜\n\n李青云提剑冲出，剑光如雪，三招两式将敌人斩于马下。敌人鲜血飞溅，他冷冷一笑，转身离去。")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        target_chars=500,
        mode=ContinueMode.USER_PLAN,
        final_plan="主角反杀，三招两式",
        context=make_ctx(),
        style=make_style(),
    )
    result = engine.generate(req)
    assert "第四章" in result.chapter_title
    assert "李青云" in result.body
    assert result.char_count > 0


def test_generate_includes_style_directive_in_prompt():
    llm = MockLLMClient()
    llm.queue_response("第四章 X\n\n正文。")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        mode=ContinueMode.USER_PLAN,
        final_plan="x",
        style=make_style(),
    )
    engine.generate(req)
    # 找到 system message
    last = llm.calls[-1]
    system_msg = next(m for m in last["messages"] if m["role"] == "system")
    assert "避免排比" in system_msg["content"]


def test_target_chars_in_system_prompt():
    llm = MockLLMClient()
    llm.queue_response("第 X 章\n\n正文")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 X 章",
        target_chars=3000,
        mode=ContinueMode.USER_PLAN,
        final_plan="x",
    )
    engine.generate(req)
    system_msg = next(m for m in llm.calls[-1]["messages"] if m["role"] == "system")
    assert "3000" in system_msg["content"]
    assert "3900" in system_msg["content"]  # 3000 * 1.3


def test_compute_generate_max_tokens_scales_with_target():
    """max_tokens 应随目标字数缩放，不能固定 4000 下限。"""
    engine = ContinueEngine(MockLLMClient())
    low = engine._compute_generate_max_tokens(500)
    mid = engine._compute_generate_max_tokens(2000)
    high = engine._compute_generate_max_tokens(5000)
    assert low < 2500
    assert low < mid < high
    assert high <= 16000


def test_generate_truncates_overlong_body():
    """正文远超目标时，服务端应在句边界兜底截断。"""
    llm = MockLLMClient()
    overlong = "李青云提剑。" + ("他挥剑斩敌。" * 200)
    llm.queue_response(f"第四章 反杀之夜\n\n{overlong}")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        target_chars=500,
        mode=ContinueMode.AUTO,
        context=make_ctx(),
    )
    result = engine.generate(req)
    assert result.char_count <= engine._char_limit(500)


def test_generate_skips_continuation_when_at_char_limit():
    """已达字数上限时不应再自动续写。"""
    llm = MockLLMClient()
    body = "他挥剑。" * 150  # 600 字，超过 400*1.3=520 上限
    llm.queue_response("第四章\n\n" + body, finish_reason="length")
    llm.queue_response("不应追加的正文。")
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        target_chars=400,
        mode=ContinueMode.AUTO,
    )
    result = engine.generate(req)
    assert "不应追加" not in result.body
    assert llm.call_count == 1
    assert result.char_count <= engine._char_limit(400)


# ---- critique (AI 重写) ----


def test_critique_requires_draft():
    llm = MockLLMClient()
    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        mode=ContinueMode.USER_PLAN,
        final_plan="x",
    )
    with pytest.raises(ValueError, match="current_draft"):
        engine.critique(req, current_draft="")


def test_critique_returns_summary_issues_and_revised():
    """两阶段：chat_json 拿 issues；再 chat 拿改写版。"""
    llm = MockLLMClient()
    issues_json = {
        "summary": "节奏稍快，打斗段可再拉长。",
        "issues": [
            {
                "category": "pacing",
                "severity": "medium",
                "description": "三招两式结束，缺少压抑→释放的弧线。",
                "suggestion": "让主角先用一招收势，引出敌人变招，再以压轴技收尾。",
                "evidence": "三招两式将敌人斩于马下。",
            },
            {
                "category": "prose",
                "severity": "low",
                "description": "形容词偏多，可换成动作。",
                "suggestion": "把'剑光如雪'换成具体的剑招名或动作。",
                "evidence": "剑光如雪",
            },
        ],
    }
    llm.queue_response(json.dumps(issues_json, ensure_ascii=False))
    llm.queue_response("第四章 反杀之夜\n\n李青云先以一剑『听风』探虚实，敌人冷笑出刀；\n他变招『惊鸿』，刀锋擦肩，最后一式『裂云』直刺咽喉。")

    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        target_chars=500,
        mode=ContinueMode.USER_PLAN,
        final_plan="主角反杀，三招两式",
        context=make_ctx(),
        style=make_style(),
    )
    result = engine.critique(
        req,
        current_draft="第四章 反杀之夜\n\n李青云提剑冲出，剑光如雪，三招两式将敌人斩于马下。",
        current_title="第四章 反杀之夜",
    )

    assert result.summary == "节奏稍快，打斗段可再拉长。"
    assert len(result.issues) == 2
    assert result.issues[0].severity == "medium"
    assert result.issues[0].category == "pacing"
    assert "听风" in result.revised_body
    assert result.revised_title == "第四章 反杀之夜"
    assert result.char_count == len(result.revised_body)

    # LLM 至少被调 2 次：1 次 chat_json 拿意见，1 次 chat 拿改写
    assert llm.call_count >= 2


def test_critique_user_plan_revise_keeps_strict_follow_directive():
    """B 动线下 critique 改写阶段也要保持「严格按规划」指令。"""
    llm = MockLLMClient()
    llm.queue_response(json.dumps({"summary": "可改", "issues": []}, ensure_ascii=False))
    llm.queue_response("第四章 X\n\n重写正文。")

    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        mode=ContinueMode.USER_PLAN,
        final_plan="主角反杀",
    )
    engine.critique(req, current_draft="第四章 X\n\n原稿。")
    # 找到改写阶段的 user prompt
    revise_call = llm.calls[-1]
    user_msg = next(m for m in revise_call["messages"] if m["role"] == "user")
    assert "B 动线" in user_msg["content"]
    assert "作者直接拟定" in user_msg["content"]


def test_critique_falls_back_to_loose_parse_on_json_failure():
    """当 chat_json 抛错时，回退到宽松解析。直接测 _loose_parse_critique。"""
    engine = ContinueEngine(MockLLMClient())
    fenced = "```json\n" + json.dumps({"summary": "草稿可改", "issues": []}, ensure_ascii=False) + "\n```"
    data = engine._loose_parse_critique(fenced)
    assert data["summary"] == "草稿可改"
    assert data["issues"] == []


def test_critique_loose_parse_returns_fallback_on_garbage():
    engine = ContinueEngine(MockLLMClient())
    data = engine._loose_parse_critique("不是 JSON，是流水文")
    assert "无法解析" in data["summary"]
    assert data["issues"] == []


def test_critique_handles_no_style_no_context():
    """即使 style/context 为空，critique 也能跑。"""
    llm = MockLLMClient()
    llm.queue_response(json.dumps({"summary": "总体可", "issues": []}, ensure_ascii=False))
    llm.queue_response("第四章 X\n\n正文。")

    engine = ContinueEngine(llm)
    req = ContinueRequest(
        book_title="测试",
        next_chapter_hint="第 4 章",
        mode=ContinueMode.USER_PLAN,
        final_plan="x",
    )
    result = engine.critique(req, current_draft="第四章 X\n\n原稿。")
    assert result.revised_body == "正文。"
