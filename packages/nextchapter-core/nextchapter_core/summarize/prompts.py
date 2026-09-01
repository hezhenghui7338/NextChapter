"""摘要 prompt 模板（对齐 Lumina segment_cloud 规则）。"""

CHAPTER_JSON_PROMPT = """你是第三方速读员。阅读以下网文章节，只输出 JSON，不要任何其他文字。你不是书中人物。

字段：
- sentences: 1～3 句概述（合计约 400 字以内；能一句说清就一句）
- bullets: 3～7 条要点，每条 {{"label":"≤8字小标题","body":"40～120字说明"}}
- sentences / bullets.body 禁止「本章」「本段」「本节」等元叙述；直接写情节与因果
- 原文自称「我」时，摘要用第一人称「我」，禁止写成「叙述者」「阅读助手」
- 人物指代须有依据，无法确认时保留不确定性

{context_block}章节：{title}
---
{text}
"""

JSON_RETRY_SUFFIX = (
    '\n\n上次输出不是合法 JSON。请只输出 '
    '{{"sentences":["…"],"bullets":[{{"label":"…","body":"…"}}]}}，不要其他文字。'
)

CONTEXT_GUIDANCE = """以下是前面章节的摘要背景，仅用于消解人物、代词与时间线：
{context}

背景使用规则：
- 只总结当前章节，不能把背景事件当作本章内容
- 本章摘要应与前文连贯，禁止出现「承接上文」等元叙述

"""
