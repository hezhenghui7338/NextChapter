"""E2E 3：续写 + 一致性检查场景。覆盖 PRD F9/F10/F11/F12。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_plan_turn_returns_assistant_message(client, mock_llm):
    """规划讨论：用户发消息，AI 回复引导。覆盖 PRD F9。"""
    mock_llm.set_callback(lambda m, kw: "建议先设计一个『身份暴露』的爽点，然后让主角在混战中展示剑法。")
    r = client.post("/continue/plan_turn", json={
        "book_title": "测试书",
        "next_chapter_hint": "第 8 章",
        "user_message": "第 8 章要怎么写？",
        "history": [],
        "context_text": "（暂无上下文）",
        "style_text": "1. 避免排比",
    })
    assert r.status_code == 200
    body = r.json()
    assert "assistant" in body
    assert len(body["assistant"]) > 0
    assert "建议" in body["assistant"]


def test_plan_turn_with_full_history(client, mock_llm):
    """多轮规划讨论：history 应正确传给 LLM。"""
    mock_llm.set_callback(lambda m, kw: "已记录你的想法。")
    r = client.post("/continue/plan_turn", json={
        "book_title": "测试书",
        "next_chapter_hint": "第 8 章",
        "user_message": "好，就按这个走",
        "history": [
            {"role": "user", "content": "第 8 章要怎么写？"},
            {"role": "assistant", "content": "建议先设计爽点。"},
            {"role": "user", "content": "想要身份暴露的爽点"},
            {"role": "assistant", "content": "好，那就在混战中暴露。"},
        ],
        "context_text": "ctx",
        "style_text": "style",
    })
    assert r.status_code == 200
    # LLM 收到的 messages 应该包含所有 history + 新 user
    last = mock_llm.calls[-1]
    msgs = last["messages"]
    # system + 4 history + 1 new user = 6
    assert len(msgs) == 6
    roles = [m["role"] for m in msgs]
    assert roles[0] == "system"
    assert roles.count("user") == 3
    assert roles.count("assistant") == 2


def test_plan_draft_returns_full_plan(client, mock_llm):
    """C 动线：一键生成规划初稿（完整 5 维）。"""
    mock_llm.set_callback(lambda m, kw: "## 剧情走向\n主角探查敌情。\n\n## 爽点\n身份暴露。")
    r = client.post("/continue/plan_draft", json={
        "book_title": "测试书",
        "next_chapter_hint": "第 8 章",
        "context_text": "前文：李青云在洛阳。",
        "style_text": "1. 避免排比",
    })
    assert r.status_code == 200
    body = r.json()
    assert "assistant" in body
    assert "剧情走向" in body["assistant"]
    system = next(m for m in mock_llm.calls[-1]["messages"] if m["role"] == "system")
    assert "起草规划初稿" in system["content"]


def test_plan_revise_rewrites_plan(client, mock_llm):
    """C 动线：根据反馈直接重写规划。"""
    mock_llm.set_callback(lambda m, kw: "## 剧情走向\n改为智取。")
    r = client.post("/continue/plan_revise", json={
        "book_title": "测试书",
        "next_chapter_hint": "第 8 章",
        "current_plan": "旧规划：硬刚反杀",
        "user_feedback": "把反杀改成智取",
        "history": [],
        "context_text": "ctx",
        "style_text": "style",
    })
    assert r.status_code == 200
    body = r.json()
    assert "智取" in body["assistant"]
    user_msg = next(m for m in mock_llm.calls[-1]["messages"] if m["role"] == "user")
    assert "上一版规划" in user_msg["content"]
    assert "把反杀改成智取" in user_msg["content"]


def test_plan_revise_rejects_empty_feedback(client, mock_llm):
    """plan_revise 空 feedback 应返回 400。"""
    r = client.post("/continue/plan_revise", json={
        "book_title": "测试书",
        "next_chapter_hint": "第 8 章",
        "current_plan": "旧规划",
        "user_feedback": "   ",
    })
    assert r.status_code == 400


def test_generate_produces_chapter(client, mock_llm):
    """B 动线：返回 chapter_title + body + char_count。覆盖 PRD F10b。"""
    mock_llm.set_callback(lambda m, kw: "第八章 身份暴露\n\n李青云猛然睁眼，发现敌人已至门外。")
    r = client.post("/continue/generate", json={
        "book_title": "测试书",
        "next_chapter_hint": "第 8 章",
        "target_chars": 2000,
        "mode": "user_plan",
        "final_plan": "主角身份暴露",
        "history": [],
        "context_text": "前文：李青云在洛阳...",
        "style_text": "1. 避免排比",
    })
    assert r.status_code == 200
    body = r.json()
    assert "第八章" in body["chapter_title"]
    assert len(body["body"]) > 0
    assert body["char_count"] == len(body["body"])


def test_generate_target_chars_in_prompt(client, mock_llm):
    """字数目标应该出现在 system prompt 里。覆盖 PRD F11。"""
    mock_llm.set_callback(lambda m, kw: "第八章\n\n正文")
    client.post("/continue/generate", json={
        "book_title": "测试",
        "next_chapter_hint": "第 8 章",
        "target_chars": 3000,
        "mode": "user_plan",
        "final_plan": "x",
    })
    system = next(m for m in mock_llm.calls[-1]["messages"] if m["role"] == "system")
    assert "3000" in system["content"]


# ---- PRD F10a：A 动线·一键续写 ----


def test_generate_auto_mode_improvises(client, mock_llm):
    """A 动线：不传 final_plan（或为空），AI 即兴续写。"""
    mock_llm.set_callback(lambda m, kw: "第八章 风云突变\n\n李青云出关，发现天色已变。")
    r = client.post("/continue/generate", json={
        "book_title": "测试书",
        "next_chapter_hint": "第 8 章",
        "target_chars": 1500,
        "mode": "auto",
        "final_plan": "",
        "context_text": "前文：李青云闭关。",
    })
    assert r.status_code == 200
    body = r.json()
    assert "第八章" in body["chapter_title"]
    # prompt 应明示 A 动线 + 即兴
    user_msg = next(m for m in mock_llm.calls[-1]["messages"] if m["role"] == "user")
    system_msg = next(m for m in mock_llm.calls[-1]["messages"] if m["role"] == "system")
    assert "A 动线" in system_msg["content"]
    assert "A 动线" in user_msg["content"]


def test_generate_auto_mode_rejects_nonempty_plan(client, mock_llm):
    """A 动线 + 非空 final_plan：服务端应返回 422（Pydantic 校验）。"""
    r = client.post("/continue/generate", json={
        "book_title": "测试",
        "next_chapter_hint": "第 8 章",
        "mode": "auto",
        "final_plan": "这个规划应该被拒绝",
    })
    assert r.status_code == 422
    detail = str(r.json()["detail"])
    assert "final_plan 必须为空" in detail or "auto" in detail


# ---- PRD F10b：B 动线·用户规划续写 ----


def test_generate_user_plan_mode_requires_plan(client, mock_llm):
    """B 动线 + 空 final_plan：服务端应返回 422。"""
    r = client.post("/continue/generate", json={
        "book_title": "测试",
        "next_chapter_hint": "第 8 章",
        "mode": "user_plan",
        "final_plan": "",
    })
    assert r.status_code == 422
    detail = str(r.json()["detail"])
    assert "final_plan 必填" in detail


def test_generate_user_plan_mode_passes_plan_to_prompt(client, mock_llm):
    """B 动线：用户的规划应该原样透传到 user prompt。"""
    mock_llm.set_callback(lambda m, kw: "第八章 X\n\n正文")
    client.post("/continue/generate", json={
        "book_title": "测试",
        "next_chapter_hint": "第 8 章",
        "mode": "user_plan",
        "final_plan": "主角修炼到元婴后期",
        "context_text": "ctx",
    })
    user_msg = next(m for m in mock_llm.calls[-1]["messages"] if m["role"] == "user")
    assert "主角修炼到元婴后期" in user_msg["content"]
    assert "作者直接拟定" in user_msg["content"]


# ---- PRD F10c：C 动线·AI 规划续写 ----


def test_generate_ai_plan_mode_requires_plan(client, mock_llm):
    """C 动线 + 空 final_plan：服务端应返回 422。"""
    r = client.post("/continue/generate", json={
        "book_title": "测试",
        "next_chapter_hint": "第 8 章",
        "mode": "ai_plan",
        "final_plan": "",
    })
    assert r.status_code == 422


def test_generate_ai_plan_mode_includes_history(client, mock_llm):
    """C 动线：plan_turn 讨论历史应该进入 prompt 的「规划讨论纪要」。"""
    mock_llm.set_callback(lambda m, kw: "第八章 X\n\n正文")
    client.post("/continue/generate", json={
        "book_title": "测试",
        "next_chapter_hint": "第 8 章",
        "mode": "ai_plan",
        "final_plan": "讨论后的最终纲要",
        "history": [
            {"role": "user", "content": "第 8 章怎么写？"},
            {"role": "assistant", "content": "建议走身份暴露路线。"},
        ],
        "context_text": "ctx",
    })
    user_msg = next(m for m in mock_llm.calls[-1]["messages"] if m["role"] == "user")
    # 透传规划 + 规划来源 + 讨论纪要
    assert "讨论后的最终纲要" in user_msg["content"]
    assert "AI 起草" in user_msg["content"]
    assert "身份暴露路线" in user_msg["content"]


def test_generate_invalid_mode_returns_422(client, mock_llm):
    """未知 mode 值应被 Pydantic Literal 拒绝。"""
    r = client.post("/continue/generate", json={
        "book_title": "测试",
        "next_chapter_hint": "第 8 章",
        "mode": "no_such_mode",
        "final_plan": "x",
    })
    assert r.status_code == 422


def test_consistency_clean(client, mock_llm):
    """一致性格局：LLM 返回空 issues → is_clean=True。覆盖 PRD F12。"""
    mock_llm.set_callback(lambda m, kw: '{"summary": "无冲突", "issues": []}')
    r = client.post("/consistency/check", json={
        "known_context": "前文：李青云在洛阳。",
        "new_chapter": "第八章\n\n李青云踏入客栈。",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["is_clean"] is True
    assert body["issues"] == []


def test_consistency_finds_issue(client, mock_llm):
    """一致性发现问题：返回 issues 列表。"""
    mock_llm.set_callback(lambda m, kw: '''{
        "summary": "发现冲突",
        "issues": [
            {"category": "character", "field": "当前状态",
             "description": "前文主角失右臂，新章用右手",
             "severity": "high", "evidence": "原文..."}
        ]
    }''')
    r = client.post("/consistency/check", json={
        "known_context": "前文：第 82 章主角失去右臂。",
        "new_chapter": "第八章\n\n李青云用右手拔剑。",
    })
    body = r.json()
    assert body["is_clean"] is False
    assert len(body["issues"]) == 1
    issue = body["issues"][0]
    assert issue["severity"] == "high"
    assert issue["category"] == "character"


def test_consistency_handles_bad_json(client, mock_llm):
    """LLM 返回非 JSON 时应优雅处理。"""
    mock_llm.set_callback(lambda m, kw: "我无法判断")
    r = client.post("/consistency/check", json={
        "known_context": "ctx",
        "new_chapter": "chapter",
    })
    assert r.status_code == 200
    body = r.json()
    # 解析失败 → is_clean=True（保守），但 summary 包含错误信息
    assert "失败" in body["summary"] or "failed" in body["summary"].lower()


def test_critique_returns_issues_and_revised(client, mock_llm):
    """AI 重写：返回 issues + 改写版正文。"""
    import json as _json

    def _cb(messages, kwargs):
        # 阶段 1：JSON 意见
        if kwargs.get("response_format") == "json":
            return _json.dumps({
                "summary": "节奏偏快。",
                "issues": [
                    {"category": "pacing", "severity": "medium",
                     "description": "三招结束太突兀", "suggestion": "加入对峙",
                     "evidence": "三招两式"},
                ],
            }, ensure_ascii=False)
        # 阶段 2：改写版正文
        return "第四章 反杀\n\n李青云以『听风』探敌，敌人出刀；他变『惊鸿』，最后『裂云』一击。"

    mock_llm.set_callback(_cb)
    r = client.post("/continue/critique", json={
        "book_title": "测试书",
        "next_chapter_hint": "第 4 章",
        "target_chars": 500,
        "mode": "user_plan",
        "final_plan": "主角反杀",
        "history": [],
        "context_text": "ctx",
        "style_text": "1. 避免排比",
        "current_title": "第四章 反杀",
        "current_draft": "第四章 反杀\n\n李青云提剑冲出，剑光如雪，三招两式将敌人斩于马下。",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == "节奏偏快。"
    assert len(body["issues"]) == 1
    assert body["issues"][0]["category"] == "pacing"
    assert "听风" in body["revised_body"]
    assert body["revised_title"] == "第四章 反杀"
    assert body["char_count"] == len(body["revised_body"])


def test_critique_requires_draft(client, mock_llm):
    """current_draft 为空时服务端应返回 400。"""
    r = client.post("/continue/critique", json={
        "book_title": "测试书",
        "next_chapter_hint": "第 4 章",
        "mode": "user_plan",
        "final_plan": "x",
        "current_draft": "",
    })
    assert r.status_code == 400
    assert "current_draft" in r.json().get("detail", "")


def test_critique_auto_mode_rejects_plan(client, mock_llm):
    """critique 在 A 动线下也拒绝非空 final_plan。"""
    r = client.post("/continue/critique", json={
        "book_title": "测试",
        "next_chapter_hint": "第 4 章",
        "mode": "auto",
        "final_plan": "不应被接受的规划",
        "current_draft": "第四章 X\n\n原稿。",
    })
    assert r.status_code == 422


def test_generate_without_api_key_returns_502(client, monkeypatch):
    """未配置 API Key 时应返回可读 502，而不是裸 500。"""
    from nextchapter_core.api import server as server_module
    from nextchapter_core.llm import LLMClient
    from nextchapter_core.writing import ContinueEngine

    monkeypatch.setattr(server_module.settings.llm, "api_key", "")
    real_llm = LLMClient(server_module.settings.llm)
    monkeypatch.setattr(server_module, "llm", real_llm)
    monkeypatch.setattr(server_module, "continue_engine", ContinueEngine(real_llm))
    r = client.post("/continue/generate", json={
        "book_title": "测试",
        "next_chapter_hint": "第 2 章",
        "target_chars": 2000,
        "mode": "auto",
        "final_plan": "",
        "history": [],
        "context_text": "上下文",
        "style_text": "风格",
    })
    assert r.status_code == 502
    assert "API Key" in r.json().get("detail", "")
