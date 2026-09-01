"""Mock LLM 客户端。

供单元测试和端到端测试使用，无需真实 API key。

两种模式：
1. 队列模式：预先 queue_response 一组字符串，依次返回。
2. 回调模式：传 callable，根据 messages 自定义返回。

所有调用都会记录到 `calls` 列表，便于断言。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

from nextchapter_core.llm import LLMClient, LLMMessage, LLMResponse


@dataclass
class MockLLMClient(LLMClient):
    """不发起任何 HTTP 调用的 LLM 客户端。"""

    _queue: List[str | tuple[str, str]] = field(default_factory=list)
    _callback: Callable[[List[LLMMessage], dict], str] | None = None
    calls: List[dict] = field(default_factory=list)
    _default_response: str = "ok"

    def __init__(self) -> None:  # noqa: D401 - intentional: 绕过父类 httpx 初始化
        # 不调用 super().__init__，避免构造 httpx.Client
        # 父类字段都得有默认值
        from nextchapter_core.config import LLMSettings
        object.__setattr__(self, "settings", LLMSettings())
        # 用一个简单的 stub 替代 _client
        self._client = None  # type: ignore[assignment]
        self._queue = []
        self._callback = None
        self.calls = []

    def queue_response(self, text: str, *, finish_reason: str = "stop") -> "MockLLMClient":
        if finish_reason == "stop":
            self._queue.append(text)
        else:
            self._queue.append((text, finish_reason))
        return self

    def set_callback(self, fn: Callable[[List[LLMMessage], dict], str]) -> "MockLLMClient":
        self._callback = fn
        return self

    def set_default(self, text: str) -> "MockLLMClient":
        self._default_response = text
        return self

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def chat(self, messages, *, temperature=0.8, max_tokens=None, response_format=None, timeout=None):
        # 记录调用
        self.calls.append({
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
            "timeout": timeout,
        })

        if self._callback is not None:
            kwargs = {"temperature": temperature, "max_tokens": max_tokens, "response_format": response_format}
            text = self._callback(messages, kwargs)
            finish_reason = "stop"
        elif self._queue:
            item = self._queue.pop(0)
            if isinstance(item, tuple):
                text, finish_reason = item
            else:
                text, finish_reason = item, "stop"
        else:
            text = self._default_response
            finish_reason = "stop"

        return LLMResponse(
            content=text,
            model="mock-model",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            finish_reason=finish_reason,
        )

    def close(self) -> None:
        pass
