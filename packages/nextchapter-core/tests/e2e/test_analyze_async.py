"""E2E：/analyze/start 后台队列 + SSE。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import pytest

from tests.support.summary_builder import build_mock_summaries


def test_analyze_start_sse(client, mock_llm, sample_novel_text):
    book = client.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    n = len(book["chapters"])
    mock_llm.set_callback(lambda m, kw: build_mock_summaries(m, kw, n, "all"))

    start = client.post("/analyze/start", json={
        "book_title": book["book_title"],
        "chapters": book["chapters"],
    })
    assert start.status_code == 200
    body = start.json()
    job_id = body["job_id"]
    assert body["total"] == n

    events = []
    deadline = time.time() + 30
    with client.stream("GET", f"/analyze/events/{job_id}") as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if time.time() > deadline:
                break
            if not line or not line.startswith("data: "):
                continue
            events.append(json.loads(line[6:]))
            if events[-1].get("type") == "analyze_done":
                break

    types = [e.get("type") for e in events]
    assert "chapter_ready" in types
    assert "analyze_done" in types
    ready = [e for e in events if e.get("type") == "chapter_ready"]
    assert len(ready) == n
    for ev in ready:
        assert len(ev.get("summaries", [])) == 3


def test_analyze_cancel(client, mock_llm, sample_novel_text, monkeypatch):
    """POST /analyze/cancel 可中止后台摘要，已完成章节保留。"""
    import threading

    from nextchapter_core.jobs import analyze_queue as analyze_queue_module

    # 取消语义按「当前波次」测试；固定 1 并发避免首波多章同时完成
    monkeypatch.setattr(analyze_queue_module, "SUMMARY_CONCURRENCY", 1)

    book = client.post("/ingest/paste", json={"text": sample_novel_text, "title": "", "author": ""}).json()
    n = len(book["chapters"])
    assert n >= 2

    # 阻塞章节摘要 LLM 调用，避免 mock 过快导致 job 在 cancel 前跑完
    hold = threading.Event()

    def gated_summaries(m, kw):
        msg = m[0].content if m else ""
        is_chapter_summary = (
            "【章节】" in msg
            or "章节：" in msg
            or "速读员" in msg
            or "把下面这章压缩" in msg
            or "把下面这章浓缩" in msg
            or "下面是章节的细摘要" in msg
        )
        if is_chapter_summary:
            hold.wait(timeout=5)
        return build_mock_summaries(m, kw, n, "all")

    mock_llm.set_callback(gated_summaries)

    start = client.post("/analyze/start", json={
        "book_title": book["book_title"],
        "chapters": book["chapters"],
    }).json()
    job_id = start["job_id"]

    # 此时后台线程应阻塞在第一章摘要；立即 cancel
    cancel = client.post(f"/analyze/cancel/{job_id}")
    assert cancel.status_code == 200

    events = []
    deadline = time.time() + 30
    hold.set()
    with client.stream("GET", f"/analyze/events/{job_id}") as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if time.time() > deadline:
                break
            if not line or not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            events.append(ev)
            if ev.get("type") in {"analyze_cancelled", "analyze_done"}:
                break

    types = [e.get("type") for e in events]
    assert "analyze_cancelled" in types
    ready = [e for e in events if e.get("type") == "chapter_ready"]
    assert 1 <= len(ready) < n
