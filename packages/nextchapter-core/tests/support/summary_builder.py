"""测试用的 mock LLM 响应生成器。

按 prompt 关键词返回合适的模拟内容，模拟真实 LLM 的行为。
"""
from __future__ import annotations

import json
import re
from typing import List

from nextchapter_core.llm import LLMMessage


# ---- 摘要 ----


_FINE_TEMPLATE = "本章讲述了 {n} 个核心事件，主角 {protagonist} 经历 {action1} 与 {action2}，关键转折在于 {twist}。主要悬念是 {cliffhanger}。"
_COARSE_TEMPLATE = "本章核心冲突：{conflict}，关键转折：{twist}，伏笔触发：{foreshadow}。"
_ULTRA_TEMPLATE = "本章推进：{advance}。"


def _extract_chapter_title(msg: str) -> str:
    m = re.search(r"【章节】([^\n]+)", msg)
    if m:
        return m.group(1).strip()
    m = re.search(r"章节：([^\n]+)", msg)
    return m.group(1).strip() if m else "unknown"


def _mock_json_fine() -> str:
    return json.dumps(
        {
            "sentences": [
                "本章讲述了 3 个核心事件，主角李青云经历击退黑衣人与救下老者，关键转折在于老者托付剑谱。"
            ],
            "bullets": [
                {"label": "遭遇", "body": "李青云在洛阳遇见黑衣人追杀，出手击退。"},
                {"label": "转折", "body": "老者托付剑谱，暗示天魔宗阴谋。"},
                {"label": "悬念", "body": "黑衣人来历不明，后文或再登场。"},
            ],
        },
        ensure_ascii=False,
    )


def build_mock_summaries(messages: List[LLMMessage], kwargs: dict, n: int, tier: str) -> str:
    """给 summarize 端点用的 mock 回调：每章一段摘要。"""
    msg = messages[0].content if messages else ""
    if "只输出 JSON" in msg and "bullets" in msg:
        return _mock_json_fine()
    title = _extract_chapter_title(msg)

    # all 模式：先 fine（从原文），后 coarse/ultra（从 fine 派生）—— mock 都用 fine 模板即可
    effective = "fine" if tier == "all" else tier
    if effective == "fine":
        text = _FINE_TEMPLATE.format(
            n=3, protagonist="李青云",
            action1="击退黑衣人", action2="救下老者",
            twist="老者托付剑谱", cliffhanger="黑衣人来历不明",
        )
    elif effective == "coarse":
        text = _COARSE_TEMPLATE.format(
            conflict="黑衣人追杀", twist="老者托付《玄天真经》", foreshadow="天魔宗阴谋",
        )
    else:  # ultra
        text = _ULTRA_TEMPLATE.format(advance="主角获剑谱，踏上峨眉之路")
    return text


# ---- 风格 ----


_MOCK_STYLE = {
    "description": (
        "句长偏好：长短句交替；"
        "修辞偏好：白描为主，少量比喻；"
        "叙事视角：第三人称；"
        "节奏特点：紧凑，开头即进入冲突；"
        "口吻特征：略带江湖气；"
        "用词特征：善用短促动作词（拔剑、刺倒、冷笑）。"
    ),
}


def build_mock_style(messages: List[LLMMessage], kwargs: dict) -> str:
    """给 /style 端点用的 mock 回调。"""
    return _MOCK_STYLE["description"]


# ---- 续写 ----


def build_mock_continuation(messages: List[LLMMessage], kwargs: dict, title: str) -> str:
    """给 /continue/generate 用的 mock 回调：返回章节标题 + 正文。"""
    body = (
        f"{title}\n\n"
        "夜深，李青云在山洞中打坐。苏清婉忽然睁开眼，低声道：有人来了。\n\n"
        "李青云猛然起身，握紧剑柄。洞口传来窸窣声响，三道黑影鱼贯而入。\n\n"
        "为首之人冷笑道：玄天真经，今日必须留下。\n\n"
        "李青云拔剑出鞘，剑光如雪。他心知对方来者不善，却也无所畏惧。"
        "三招两式间，已将一名黑衣人刺倒。剩余两人对视一眼，同时出招。\n\n"
        "混战中，李青云不慎被暗器划伤右臂。他咬牙不退，反手一剑封喉。\n\n"
        "苏清婉趁机出手，软剑如蛇，将另一人钉在石壁上。\n\n"
        "战后，两人相视而笑。真正的对决，才刚刚开始。"
    )
    return body


# ---- 一致性 ----


def build_mock_consistency_issues() -> str:
    """给 /consistency/check 用的 mock 回调。"""
    return json.dumps({
        "summary": "发现 1 处冲突：角色身体状态前后不一致",
        "issues": [
            {
                "category": "character",
                "field": "人物-当前状态",
                "description": "前文李青云右臂已受伤，新章节却用右手流畅出招，未见包扎或替换",
                "severity": "high",
                "evidence": "前文：『右臂鲜血直流』；新章：『他拔剑出鞘』『反手一剑封喉』",
            }
        ]
    }, ensure_ascii=False)


def build_mock_no_issues() -> str:
    return json.dumps({"summary": "无明显冲突", "issues": []}, ensure_ascii=False)
