"""LLM 客户端：支持 OpenAI 兼容协议（DeepSeek/Moonshot/通义等）+ Anthropic。"""
from .client import LLMClient, LLMError, LLMMessage, LLMResponse

__all__ = ["LLMClient", "LLMError", "LLMMessage", "LLMResponse"]
