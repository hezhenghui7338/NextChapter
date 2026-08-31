"""一致性检查测试。覆盖 PRD F12：续写后 LLM 扫描冲突。"""
import json

import pytest

from nextchapter_core.consistency import CheckResult, ConsistencyChecker, ConsistencyIssue
from tests.support.mock_llm import MockLLMClient

pytestmark = pytest.mark.unit


def test_check_no_issues():
    llm = MockLLMClient()
    llm.queue_response(json.dumps({
        "summary": "无明显冲突",
        "issues": []
    }, ensure_ascii=False))
    checker = ConsistencyChecker(llm)
    r = checker.check("主角在洛阳城，筑基中期。", "李青云踏入客栈，遇见一位老者。")
    assert r.is_clean
    assert r.summary == "无明显冲突"
    assert r.issues == []


def test_check_finds_issue():
    llm = MockLLMClient()
    llm.queue_response(json.dumps({
        "summary": "发现 1 处冲突",
        "issues": [
            {
                "category": "character",
                "field": "人物-当前状态",
                "description": "前文主角已失去右臂，新章节却使用右手持剑",
                "severity": "high",
                "evidence": "前文第 82 章：李青云右臂已断；新章：李青云右手握剑"
            }
        ]
    }, ensure_ascii=False))
    checker = ConsistencyChecker(llm)
    r = checker.check(
        "前文第 82 章：李青云在战斗中失去右臂。",
        "李青云右手握剑，刺向敌人。"
    )
    assert not r.is_clean
    assert len(r.issues) == 1
    issue = r.issues[0]
    assert issue.category == "character"
    assert issue.severity == "high"
    assert "右臂" in issue.description


def test_check_handles_json_with_fence():
    """LLM 经常返回 ```json ... ``` 围栏，必须能解析。"""
    llm = MockLLMClient()
    llm.queue_response('```json\n{"summary": "ok", "issues": []}\n```')
    checker = ConsistencyChecker(llm)
    r = checker.check("ctx", "new")
    assert r.is_clean


def test_check_handles_invalid_json_gracefully():
    llm = MockLLMClient()
    llm.queue_response("not json at all")
    checker = ConsistencyChecker(llm)
    r = checker.check("ctx", "new")
    # 解析失败时，summary 应有错误信息
    assert r.is_clean  # 没有 issues
    assert "失败" in r.summary or "failed" in r.summary.lower()


def test_check_result_to_dict():
    """CheckResult 序列化为 dict（API 返回用）。"""
    r = CheckResult(
        issues=[ConsistencyIssue(category="plot", field="伏笔", description="x", severity="low")],
        summary="有冲突"
    )
    d = r.to_dict()
    assert d["is_clean"] is False
    assert len(d["issues"]) == 1
    assert d["issues"][0]["category"] == "plot"
