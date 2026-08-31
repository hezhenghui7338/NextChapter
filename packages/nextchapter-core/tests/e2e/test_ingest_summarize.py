"""E2E 2：导入 + 摘要场景。覆盖 PRD F1/F2/F3/F4/F5。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_ingest_paste_extracts_title_and_author(client, sample_novel_text):
    """从书开头几行识别《书名》和作者：X。"""
    r = client.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""})
    body = r.json()
    assert body["book_title"] == "青云剑诀"
    assert body["author"] == "墨羽青鸾"
    assert body["char_count"] > 1000


def test_ingest_paste_falls_back_to_default_title(client):
    """没有元数据的文本应使用 fallback 标题。"""
    text = "第一章 测试\n\n" + "正文内容" * 30
    r = client.post("/ingest/paste", json={"text": text, "title": "", "author": ""})
    body = r.json()
    assert body["book_title"] == "未命名作品"
    assert body["author"] == ""


def test_ingest_path_with_short_novel(client, books_dir):
    """短篇测试：3 章。"""
    r = client.post("/ingest/path", json={"path": str(books_dir / "short_novel.txt")})
    assert r.status_code == 200
    body = r.json()
    assert body["book_title"] == "短篇测试"
    chapters = body["chapters"]
    assert any("第一章" in c["title"] for c in chapters)


def test_ingest_path_404(client, tmp_path):
    """不存在的路径应返回 404。"""
    r = client.post("/ingest/path", json={"path": str(tmp_path / "nope.txt")})
    assert r.status_code == 404


def test_summarize_with_specific_indices(client, mock_llm, sample_novel_text):
    """可以只对部分章节做摘要。"""
    from tests.support.summary_builder import build_mock_summaries
    book = client.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    chapters = book["chapters"]
    mock_llm.set_callback(lambda m, kw: build_mock_summaries(m, kw, 2, "fine"))

    r = client.post("/summarize", json={
        "book_title": "青云剑诀",
        "chapters": chapters,
        "tier": "fine",
        "indices": [0, 1],
    })
    assert r.status_code == 200
    summaries = r.json()["summaries"]
    # 只对前 2 章做摘要
    assert len(summaries) == 2
    assert summaries[0]["chapter_index"] == 0
    assert summaries[1]["chapter_index"] == 1


def test_summarize_invalid_tier(client, sample_novel_text):
    """无效的 tier 应返回 400。"""
    book = client.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    r = client.post("/summarize", json={
        "book_title": "青云剑诀",
        "chapters": book["chapters"],
        "tier": "invalid",
    })
    assert r.status_code == 400


def test_summarize_chinese_char_count(mock_llm, sample_novel_text):
    """fine 档摘要应该在 100-300 字符之间（PRD F3）。"""
    from tests.support.summary_builder import build_mock_summaries
    book = client_post = None
    from fastapi.testclient import TestClient
    from nextchapter_core.api import server as server_module
    from nextchapter_core.summarize import Summarizer
    from nextchapter_core.style import StyleProfiler
    from nextchapter_core.writing import ContinueEngine
    from nextchapter_core.consistency import ConsistencyChecker

    server_module.llm = mock_llm
    server_module.summarizer = Summarizer(mock_llm)
    server_module.style_profiler = StyleProfiler(mock_llm, server_module.settings.style)
    server_module.continue_engine = ContinueEngine(mock_llm)
    server_module.checker = ConsistencyChecker(mock_llm)
    client = TestClient(server_module.app)

    book = client.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    mock_llm.set_callback(lambda m, kw: build_mock_summaries(m, kw, len(book["chapters"]), "fine"))
    r = client.post("/summarize", json={"book_title": "青云剑诀", "chapters": book["chapters"], "tier": "fine"})
    summaries = r.json()["summaries"]
    for s in summaries:
        assert 30 < len(s["text"]) < 300, f"summary too short/long: {len(s['text'])} chars"
