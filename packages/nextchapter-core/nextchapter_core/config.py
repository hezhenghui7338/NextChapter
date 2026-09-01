"""配置管理：环境变量 + 配置文件 + 运行时覆盖。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# 默认 sidecar 端口（避免和 Lumina 的 17432 冲突）
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18432


@dataclass
class LLMSettings:
    """云端 LLM 配置（DeepSeek/Claude/OpenAI 兼容协议）。"""

    provider: str = "deepseek"  # deepseek | openai | anthropic
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    timeout: float = 180.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "LLMSettings":
        return cls(
            provider=os.getenv("NC_LLM_PROVIDER", "deepseek"),
            api_key=os.getenv("NC_LLM_API_KEY", ""),
            base_url=os.getenv("NC_LLM_BASE_URL", "https://api.deepseek.com/v1"),
            model=os.getenv("NC_LLM_MODEL", "deepseek-chat"),
            timeout=float(os.getenv("NC_LLM_TIMEOUT", "180")),
            max_retries=int(os.getenv("NC_LLM_MAX_RETRIES", "3")),
        )


# 摘要策略（对齐 Lumina segment 参数）
CHAPTER_TEXT_MAX_CHARS = int(os.getenv("NC_CHAPTER_TEXT_MAX", "4000"))
SUMMARY_CONTEXT_MAX_CHARS = int(os.getenv("NC_SUMMARY_CONTEXT_MAX", "1600"))
SUMMARY_CONTEXT_QUERY_LIMIT = int(os.getenv("NC_SUMMARY_CONTEXT_LIMIT", "8"))
SUMMARY_LLM_MAX_RETRIES = int(os.getenv("NC_SUMMARY_LLM_RETRIES", "3"))
SUMMARY_SEGMENT_TIMEOUT_SECONDS = float(os.getenv("NC_SUMMARY_TIMEOUT", "180"))
SUMMARY_FINE_MAX_TOKENS = int(os.getenv("NC_SUMMARY_FINE_TOKENS", "768"))
SUMMARY_DERIVED_MAX_TOKENS = int(os.getenv("NC_SUMMARY_DERIVED_TOKENS", "400"))
SUMMARY_CONCURRENCY = max(1, int(os.getenv("NC_SUMMARY_CONCURRENCY", "8")))


@dataclass
class ContextSettings:
    """滑动窗口 + 分级压缩策略。"""

    # 25 章窗口内的分级
    recent_chapter_count: int = 5      # 最近 5 章：细摘要
    middle_chapter_count: int = 10     # 中间 10 章：粗摘要
    far_chapter_count: int = 10        # 远端 10 章：极致压缩
    # 单章摘要目标长度（中文字符数）
    fine_summary_chars: int = 400
    coarse_summary_chars: int = 150
    ultra_summary_chars: int = 60

    @classmethod
    def from_env(cls) -> "ContextSettings":
        return cls(
            recent_chapter_count=int(os.getenv("NC_CONTEXT_RECENT", "5")),
            middle_chapter_count=int(os.getenv("NC_CONTEXT_MIDDLE", "10")),
            far_chapter_count=int(os.getenv("NC_CONTEXT_FAR", "10")),
        )


@dataclass
class StyleSettings:
    """风格向量 + 反 AI 味提示词。"""

    few_shot_chapters: int = 3  # 抽取前 N 章做 few-shot 风格样本
    anti_ai_preset: str = "default"  # default | strong | mild

    @classmethod
    def from_env(cls) -> "StyleSettings":
        preset = os.getenv("NC_ANTI_AI_PRESET", "default")
        # 防御：未知值回退到 default
        if preset not in {"default", "strong", "mild"}:
            preset = "default"
        return cls(anti_ai_preset=preset)


@dataclass
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings.from_env)
    context: ContextSettings = field(default_factory=ContextSettings)
    style: StyleSettings = field(default_factory=StyleSettings)
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    data_dir: Path = field(default_factory=lambda: Path.home() / ".nextchapter")


def load_settings() -> Settings:
    """从环境加载设置。后续会支持配置文件。"""
    s = Settings()
    s.llm = LLMSettings.from_env()
    s.context = ContextSettings.from_env()
    s.style = StyleSettings.from_env()
    s.host = os.getenv("NC_HOST", DEFAULT_HOST)
    s.port = int(os.getenv("NC_PORT", str(DEFAULT_PORT)))
    if env_dir := os.getenv("NC_DATA_DIR"):
        s.data_dir = Path(env_dir)
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
