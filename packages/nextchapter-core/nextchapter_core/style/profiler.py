"""风格 profiler。

借鉴思路 + 反 AI 味提示词：
1. 从作者前 N 章提取 few-shot 样本（直接抽 1-2 段原文）
2. 用 LLM 抽取风格特征（句长、修辞、口吻、节奏偏好）
3. 注入续写 prompt + 反 AI 味提示词
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..chunker import Chapter
from ..config import StyleSettings
from ..llm import LLMClient, LLMMessage


ANTI_AI_PRESETS = {
    "default": (
        "写作约束：\n"
        "1. 避免排比句堆叠（连续 3 句以上结构相似的句子）。\n"
        "2. 避免空洞的抒情与总结升华，不要在章末做主题拔高。\n"
        "3. 避免『他不知道的是，这仅仅是开始』这类全知预告。\n"
        "4. 对话要口语化、符合人物身份，不使用书面腔。\n"
        "5. 动作描写具体，避免『眼神中闪过一丝复杂的情绪』这种万金油句式。\n"
        "6. 保持网文的『代入感』节奏：人物立刻有反应，情节有推进。\n"
    ),
    "strong": (
        "严格反 AI 味：\n"
        "1. 禁止使用任何形式的排比 / 对仗 / 三连句。\n"
        "2. 禁止章末抒情、禁止主题升华、禁止『这一切，仅仅是开始』。\n"
        "3. 禁止『他不知道的是』『她心中涌起一股暖流』类全知旁白。\n"
        "4. 禁止空洞修辞：眼神复杂、嘴角微扬、心中五味杂陈等。\n"
        "5. 对话要像真人说话，不端着。\n"
        "6. 情节推进要快，每段要有信息量。\n"
    ),
    "mild": (
        "写作提示：\n"
        "1. 减少空洞抒情。\n"
        "2. 对话自然。\n"
        "3. 节奏紧凑。\n"
    ),
}


@dataclass
class StyleProfile:
    samples: List[str] = field(default_factory=list)        # few-shot 原文片段
    description: str = ""                                   # LLM 抽出的风格描述
    anti_ai_directive: str = ""                             # 反 AI 味提示词


class StyleProfiler:
    def __init__(self, llm: LLMClient, settings: StyleSettings):
        self.llm = llm
        self.settings = settings

    def profile(self, chapters: List[Chapter]) -> StyleProfile:
        """从前 N 章抽取风格样本 + 描述。"""
        few_shot = self._extract_samples(chapters)
        description = self._describe_style(few_shot) if few_shot else ""
        directive = ANTI_AI_PRESETS.get(self.settings.anti_ai_preset, ANTI_AI_PRESETS["default"])
        return StyleProfile(samples=few_shot, description=description, anti_ai_directive=directive)

    def render(self, profile: StyleProfile) -> str:
        """拼成可注入 prompt 的风格模块（实例方法封装）。"""
        return self._render_profile(profile)

    @staticmethod
    def _render_profile(profile: StyleProfile) -> str:
        """无状态版本，供其他模块直接调用（如 writing engine）。"""
        parts: list[str] = []
        if profile.anti_ai_directive:
            parts.append(profile.anti_ai_directive)
        if profile.description:
            parts.append(f"\n【原作风格】\n{profile.description}")
        if profile.samples:
            parts.append("\n【作者原文片段（few-shot）】")
            for i, s in enumerate(profile.samples, 1):
                parts.append(f"—— 样本 {i} ——\n{s[:500]}")
        return "\n".join(parts)

    # ---- internals ----

    def _extract_samples(self, chapters: List[Chapter]) -> List[str]:
        """从前 N 章各取 1-2 段（跳过纯对话章节）。"""
        out: List[str] = []
        for ch in chapters[: self.settings.few_shot_chapters]:
            # 取章节中间一段，避开开头章名和章末空行
            body = ch.body.strip()
            if len(body) < 100:
                continue
            mid = len(body) // 2
            seg = body[max(0, mid - 300) : mid + 300]
            out.append(seg.strip())
        return out

    def _describe_style(self, samples: List[str]) -> str:
        joined = "\n\n".join(f"【样本{i+1}】\n{s}" for i, s in enumerate(samples))
        msg = LLMMessage(
            "user",
            f"下面是某中文网文作者的原文片段。请用 200 字以内客观描述其写作风格：\n"
            f"- 句长偏好（短句/长句/长短交替）\n"
            f"- 修辞偏好（比喻/排比/白描/其它）\n"
            f"- 叙事视角（第一人称/第三人称/混合）\n"
            f"- 节奏特点（紧凑/舒缓/快慢交替）\n"
            f"- 口吻特征（口语/书面/江湖气/古风等）\n"
            f"- 用词特征（是否大量使用网文常见套路词、是否有独特金句）\n\n"
            f"{joined}\n\n"
            f"输出结构化描述，每条一行。不要举例。",
        )
        try:
            resp = self.llm.chat([msg], temperature=0.3, max_tokens=400)
            return resp.content.strip()
        except Exception:
            return ""
