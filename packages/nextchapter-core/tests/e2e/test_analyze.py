"""端到端：/analyze 端点（一步：风格 + 三档摘要）+ 增量模式。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import pytest
from fastapi.testclient import TestClient

import nextchapter_core.api.server as server_module
from nextchapter_core.summarize import Summarizer
from nextchapter_core.style import StyleProfiler
from nextchapter_core.writing import ContinueEngine
from nextchapter_core.consistency import ConsistencyChecker


@pytest.fixture
def client_with_mock(mock_llm, sample_novel_text):
    """重置 sidecar 模块里的 LLM 客户端为 mock。"""
    server_module.llm = mock_llm
    server_module.summarizer = Summarizer(mock_llm)
    server_module.style_profiler = StyleProfiler(mock_llm, server_module.settings.style)
    server_module.continue_engine = ContinueEngine(mock_llm)
    server_module.checker = ConsistencyChecker(mock_llm)
    return TestClient(server_module.app)


def test_analyze_full(client_with_mock, mock_llm, sample_novel_text):
    """不传 indices → 全部章节一次性生成 fine/coarse/ultra。"""
    from tests.support.summary_builder import build_mock_summaries
    book = client_with_mock.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    n = len(book["chapters"])
    # mock 同时响应风格 + 三档摘要（key 含 tier 标识）
    mock_llm.set_callback(lambda m, kw: build_mock_summaries(m, kw, n, "all"))
    r = client_with_mock.post("/analyze", json={
        "book_title": book["book_title"],
        "chapters": book["chapters"],
    })
    assert r.status_code == 200
    body = r.json()
    # 风格字段都在
    assert "style_description" in body
    assert "anti_ai_directive" in body
    assert isinstance(body["style_samples"], list)
    # 摘要：每章 3 档 = n * 3
    assert len(body["summaries"]) == n * 3
    tiers = [s["tier"] for s in body["summaries"]]
    assert tiers.count("fine") == n
    assert tiers.count("coarse") == n
    assert tiers.count("ultra") == n
    # 每章三档的 chapter_index 一致
    for idx in range(n):
        idx_tiers = [s["tier"] for s in body["summaries"] if s["chapter_index"] == idx]
        assert sorted(idx_tiers) == ["coarse", "fine", "ultra"]


def test_analyze_incremental(client_with_mock, mock_llm, sample_novel_text):
    """传 indices → 只摘要指定章节；老摘要不动。"""
    from tests.support.summary_builder import build_mock_summaries
    book = client_with_mock.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    n = len(book["chapters"])
    target_idx = [0, 2]  # 只摘要前两章和第 3 章
    mock_llm.set_callback(lambda m, kw: build_mock_summaries(m, kw, len(target_idx), "all"))
    r = client_with_mock.post("/analyze", json={
        "book_title": book["book_title"],
        "chapters": book["chapters"],
        "indices": target_idx,
    })
    assert r.status_code == 200
    body = r.json()
    # 增量：每个目标章节 3 档 → 2 * 3 = 6
    assert len(body["summaries"]) == len(target_idx) * 3
    for s in body["summaries"]:
        assert s["chapter_index"] in set(target_idx)


def test_summarize_tier_all(client_with_mock, mock_llm, sample_novel_text):
    """/summarize 的 tier="all" 一次返回三档。"""
    from tests.support.summary_builder import build_mock_summaries
    book = client_with_mock.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    n = len(book["chapters"])
    mock_llm.set_callback(lambda m, kw: build_mock_summaries(m, kw, n, "all"))
    r = client_with_mock.post("/summarize", json={
        "book_title": book["book_title"],
        "chapters": book["chapters"],
        "tier": "all",
    })
    assert r.status_code == 200
    summaries = r.json()["summaries"]
    assert len(summaries) == n * 3


def test_analyze_then_context_build(client_with_mock, mock_llm, sample_novel_text):
    """完整 E2E：/analyze 拿到三档 → 用 /context/build 拼滑动窗口。"""
    from tests.support.summary_builder import build_mock_summaries
    book = client_with_mock.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    n = len(book["chapters"])
    mock_llm.set_callback(lambda m, kw: build_mock_summaries(m, kw, n, "all"))
    r = client_with_mock.post("/analyze", json={
        "book_title": book["book_title"],
        "chapters": book["chapters"],
    })
    assert r.status_code == 200
    summaries = r.json()["summaries"]
    # 用 fine 档走 context/build
    fine_only = [s for s in summaries if s["tier"] == "fine"]
    assert len(fine_only) == n
    r2 = client_with_mock.post("/context/build", json={
        "summaries": fine_only,
        "total_chapters": n,
    })
    assert r2.status_code == 200
    ctx = r2.json()
    # 短书全部进 fine
    assert ctx["fine_count"] == n
    assert ctx["coarse_count"] == 0
    assert ctx["ultra_count"] == 0
    # rendered 包含章节标题
    for s in fine_only:
        assert s["title"] in ctx["rendered"]
