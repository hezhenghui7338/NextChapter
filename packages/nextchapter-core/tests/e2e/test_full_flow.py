"""E2E 1：完整流程 — 粘贴导入 → 章节切分 → 三档摘要 → 风格抽取 → 上下文窗口 → 规划讨论 → 一键续写 → 一致性检查。

覆盖 PRD 主要功能：F1/F2/F3/F4/F5/F6/F7/F8/F9/F10/F12。
"""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.e2e


def test_health(client):
    """E1: sidecar 健康检查。"""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "pid" in body
    assert "plan_draft" in body.get("features", [])
    assert "llm_configured" in body


def test_ingest_paste_splits_into_chapters(client, sample_novel_text):
    """E2: 粘贴导入 + 章节切分。覆盖 PRD F1/F2。"""
    r = client.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["book_title"] == "青云剑诀"
    assert body["author"] == "墨羽青鸾"
    chapters = body["chapters"]
    # 序章 + 6 章 = 7 个
    assert len(chapters) >= 6
    titles = [c["title"] for c in chapters]
    assert any("序章" in t or "楔子" in t for t in titles)
    assert any("第一章" in t for t in titles)
    assert any("第六章" in t for t in titles)


def test_ingest_paste_no_chapter_falls_back(client, no_chapter_text):
    """E3: 无章节标记的文本应整体识别为单章。"""
    r = client.post("/ingest/paste", json={"text": no_chapter_text, "title": "", "author": ""})
    assert r.status_code == 200
    chapters = r.json()["chapters"]
    assert len(chapters) == 1


def test_ingest_path_with_sample_file(client, books_dir):
    """E4: 文件路径导入。"""
    sample = books_dir / "sample_novel.txt"
    r = client.post("/ingest/path", json={"path": str(sample)})
    assert r.status_code == 200
    assert r.json()["book_title"] == "青云剑诀"


def test_summarize_three_tiers(client, mock_llm, sample_novel_text):
    """E5: 摘要生成 — 三档。覆盖 PRD F3/F4/F5。

    准备 N 段 mock 响应（每章一段），用 summary 工具生成。
    """
    from tests.support.summary_builder import build_mock_summaries
    book_resp = client.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    chapters = book_resp["chapters"]
    n = len(chapters)
    mock_llm.set_callback(lambda msgs, kw: build_mock_summaries(msgs, kw, n, tier="fine"))

    # fine 档
    r = client.post("/summarize", json={"book_title": "青云剑诀", "chapters": chapters, "tier": "fine"})
    assert r.status_code == 200
    fine = r.json()["summaries"]
    assert len(fine) == n
    for s in fine:
        assert s["tier"] == "fine"
        assert 30 < len(s["text"]) < 300  # mock 摘要控制在 100-200 字

    # coarse 档
    mock_llm.set_callback(lambda msgs, kw: build_mock_summaries(msgs, kw, n, tier="coarse"))
    r = client.post("/summarize", json={"book_title": "青云剑诀", "chapters": chapters, "tier": "coarse"})
    assert r.status_code == 200
    coarse = r.json()["summaries"]
    assert len(coarse) == n
    for s in coarse:
        assert s["tier"] == "coarse"

    # ultra 档
    mock_llm.set_callback(lambda msgs, kw: build_mock_summaries(msgs, kw, n, tier="ultra"))
    r = client.post("/summarize", json={"book_title": "青云剑诀", "chapters": chapters, "tier": "ultra"})
    assert r.status_code == 200
    ultra = r.json()["summaries"]
    assert len(ultra) == n
    for s in ultra:
        assert s["tier"] == "ultra"


def test_style_extraction(client, mock_llm, books_dir):
    """E6: 风格向量抽取。覆盖 PRD F7/F8。"""
    from tests.support.summary_builder import build_mock_style
    mock_llm.set_callback(build_mock_style)

    sample = books_dir / "sample_novel.txt"
    r = client.post("/ingest/path", json={"path": str(sample)})
    chapters = r.json()["chapters"][:3]

    r = client.post("/style", json={"book_title": "青云剑诀", "samples": chapters})
    assert r.status_code == 200
    body = r.json()
    assert "description" in body
    assert "anti_ai_directive" in body
    assert "samples" in body
    # 反 AI 味提示词应该非空
    assert len(body["anti_ai_directive"]) > 50
    # 样本数量 = 配置的 few_shot_chapters（默认 3）
    assert len(body["samples"]) == 3


def test_context_build_for_short_book(client, sample_novel_text):
    """E7: 短书（< 25 章）全部进 fine。覆盖 PRD F6。"""
    r = client.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    n = len(r["chapters"])
    # 假装全部章节都有 fine 摘要
    fine_summaries = [
        {"chapter_index": i, "title": r["chapters"][i]["title"], "tier": "fine", "text": f"summary {i}"}
        for i in range(n)
    ]
    r = client.post("/context/build", json={"summaries": fine_summaries, "total_chapters": n})
    assert r.status_code == 200
    body = r.json()
    # 短书：全部进 fine
    assert body["fine_count"] == n
    assert body["coarse_count"] == 0
    assert body["ultra_count"] == 0
    assert "近期剧情细摘要" in body["rendered"]


def test_context_build_for_long_book(client):
    """E8: 长书（> 25 章）按 5+10+10 分级。覆盖 PRD F6。"""
    fine = [
        {"chapter_index": i, "title": f"第{i+1}章", "tier": "fine", "text": f"summary {i}"}
        for i in range(40)
    ]
    r = client.post("/context/build", json={"summaries": fine, "total_chapters": 40})
    assert r.status_code == 200
    body = r.json()
    assert body["fine_count"] == 5
    assert body["coarse_count"] == 10
    assert body["ultra_count"] == 10


def test_full_continue_flow(client, mock_llm, books_dir):
    """E9: 完整续写流程 — 导入 → 风格 → 摘要 → 上下文 → 规划 → 一键续写 → 一致性检查。

    这是端到端最关键的一条：模拟一个用户的完整工作流。
    覆盖 PRD F1/F2/F3/F7/F8/F9/F10/F12。
    """
    from tests.support.summary_builder import (
        build_mock_summaries,
        build_mock_style,
        build_mock_continuation,
        build_mock_consistency_issues,
    )

    sample = books_dir / "sample_novel.txt"

    # 1) 导入
    r = client.post("/ingest/path", json={"path": str(sample)})
    assert r.status_code == 200
    book = r.json()
    chapters = book["chapters"]
    n = len(chapters)
    assert n >= 6

    # 2) 风格抽取
    mock_llm.set_callback(build_mock_style)
    r = client.post("/style", json={"book_title": book["book_title"], "samples": chapters[:3]})
    style = r.json()

    # 3) 摘要（fine 档）
    mock_llm.set_callback(lambda m, kw: build_mock_summaries(m, kw, n, "fine"))
    r = client.post("/summarize", json={"book_title": book["book_title"], "chapters": chapters, "tier": "fine"})
    summaries = r.json()["summaries"]

    # 4) 上下文窗口
    r = client.post("/context/build", json={"summaries": summaries, "total_chapters": n})
    ctx = r.json()

    # 5) 规划讨论
    mock_llm.set_callback(lambda m, kw: "建议先设计一个『身份暴露』的爽点。")
    r = client.post("/continue/plan_turn", json={
        "book_title": book["book_title"],
        "next_chapter_hint": "第 8 章",
        "user_message": "我想要一个身份暴露的爽点。",
        "history": [],
        "context_text": ctx["rendered"],
        "style_text": f"{style['anti_ai_directive']}\n{style['description']}",
    })
    assert r.status_code == 200
    plan_resp = r.json()
    assert "爽点" in plan_resp["assistant"]

    # 6) AI 规划续写（C 动线）：把规划讨论的结果作为 final_plan 锁定后生成
    mock_llm.set_callback(lambda m, kw: build_mock_continuation(m, kw, "第 8 章 身份暴露"))
    r = client.post("/continue/generate", json={
        "book_title": book["book_title"],
        "next_chapter_hint": "第 8 章",
        "target_chars": 2000,
        "mode": "ai_plan",
        "final_plan": "主角身份暴露，三招两式击败埋伏的敌人",
        "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
        "context_text": ctx["rendered"],
        "style_text": f"{style['anti_ai_directive']}\n{style['description']}",
    })
    assert r.status_code == 200
    chapter = r.json()
    assert "第 8 章" in chapter["chapter_title"]
    assert len(chapter["body"]) > 100
    assert chapter["char_count"] == len(chapter["body"])

    # 7) 一致性检查
    mock_llm.set_callback(lambda m, kw: build_mock_consistency_issues())
    r = client.post("/consistency/check", json={
        "known_context": ctx["rendered"],
        "new_chapter": chapter["chapter_title"] + "\n\n" + chapter["body"],
    })
    assert r.status_code == 200
    check = r.json()
    assert "summary" in check
    assert "issues" in check
    assert isinstance(check["is_clean"], bool)
