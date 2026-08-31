"""轻量一致性检查（MVP）。

策略：续写后用 LLM 一次性扫描「续写正文 vs 已知事实」，输出结构化冲突列表。
完整版（P1）：独立 fact-bank 维护 + 主动校验。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List

from ..llm import LLMClient, LLMMessage

log = logging.getLogger("nextchapter.consistency")


@dataclass
class ConsistencyIssue:
    category: str        # character | world | plot
    field: str           # 人物-年龄 / 人物-当前状态 / 世界-地点 / 剧情-已发生事件 ...
    description: str     # 人类可读的描述
    severity: str        # high | medium | low
    evidence: str = ""   # 出处（原文片段）


@dataclass
class CheckResult:
    issues: List[ConsistencyIssue] = field(default_factory=list)
    summary: str = ""

    @property
    def is_clean(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        return {
            "is_clean": self.is_clean,
            "summary": self.summary,
            "issues": [
                {
                    "category": i.category,
                    "field": i.field,
                    "description": i.description,
                    "severity": i.severity,
                    "evidence": i.evidence,
                }
                for i in self.issues
            ],
        }


class ConsistencyChecker:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def check(self, known_context: str, new_chapter: str) -> CheckResult:
        """已知上下文 vs 新续写章节 → 冲突列表。"""
        prompt = self._build_prompt(known_context, new_chapter)
        try:
            data = self.llm.chat_json([prompt], temperature=0.2, max_tokens=2000)
        except Exception as e:
            log.warning("consistency check failed: %s", e)
            return CheckResult(summary=f"检查失败：{e}")

        issues: List[ConsistencyIssue] = []
        for item in data.get("issues", []) or []:
            try:
                issues.append(
                    ConsistencyIssue(
                        category=item.get("category", "plot"),
                        field=item.get("field", ""),
                        description=item.get("description", ""),
                        severity=item.get("severity", "medium"),
                        evidence=item.get("evidence", ""),
                    )
                )
            except Exception as e:
                log.warning("skip malformed issue: %s", e)

        return CheckResult(issues=issues, summary=data.get("summary", ""))

    def _build_prompt(self, known_context: str, new_chapter: str) -> LLMMessage:
        return LLMMessage(
            "user",
            f"你是网文一致性检查助手。请对比【已知前情】与【新续写章节】，找出可能的一致性冲突。\n\n"
            f"【已知前情】\n{known_context[:6000]}\n\n"
            f"【新续写章节】\n{new_chapter[:4000]}\n\n"
            f"检查维度：\n"
            f"1. 人物：年龄、身份、性格、当前状态（身体/位置/装备/境界）、生死、能力\n"
            f"2. 世界：地点、时间、势力、规则（功法/境界/科技）\n"
            f"3. 剧情：已发生事件、未解决事件、伏笔、人际关系\n\n"
            f"输出 JSON，结构：\n"
            f"{{\n"
            f'  "summary": "一句话总结（是否有冲突、严重程度）",\n'
            f'  "issues": [\n'
            f'    {{"category": "character|world|plot", "field": "维度", "description": "冲突描述", '
            f'"severity": "high|medium|low", "evidence": "原文片段或前后文引用"}}\n'
            f"  ]\n"
            f"}}\n"
            f"如果没发现冲突，issues 留空，summary 写『无明显冲突』。\n"
            f"只在确实冲突时才报告，宁可漏报不要误报。",
        )
