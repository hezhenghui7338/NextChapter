"""LLM 客户端实现。

优先用 OpenAI 兼容协议（DeepSeek/Moonshot/通义千问/OpenAI 自身）。
Anthropic 单独走 SDK。
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from ..config import LLMSettings

log = logging.getLogger("nextchapter.llm")


@dataclass
class LLMMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    raw: Optional[Dict[str, Any]] = None
    # OpenAI 风格的 finish_reason: "stop" | "length" | "content_filter" | "tool_calls" | None
    # "length" 表示 max_tokens 不够导致输出被截断
    finish_reason: Optional[str] = None


class LLMError(RuntimeError):
    pass


class LLMClient:
    """云端 LLM 客户端。

    使用方式：
        client = LLMClient(settings.llm)
        resp = client.chat([LLMMessage("user", "你好")])
    """

    def __init__(self, settings: LLMSettings):
        self.settings = settings
        self._client = httpx.Client(timeout=settings.timeout)

    # ---- public ----

    def chat(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.8,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,  # "json" | None
    ) -> LLMResponse:
        self._ensure_api_key()
        if self.settings.provider == "anthropic":
            return self._chat_anthropic(messages, temperature, max_tokens)
        return self._chat_openai_compat(messages, temperature, max_tokens, response_format)

    def chat_json(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """结构化输出场景：强制 JSON。"""
        resp = self.chat(messages, temperature=temperature, max_tokens=max_tokens, response_format="json")
        return self._parse_json(resp.content)

    # ---- internals ----

    def _chat_openai_compat(
        self,
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: Optional[int],
        response_format: Optional[str],
    ) -> LLMResponse:
        url = f"{self.settings.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.api_key}",
        }
        payload: Dict[str, Any] = {
            "model": self.settings.model,
            "messages": [self._msg_to_dict(m) for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        last_err: Optional[Exception] = None
        for attempt in range(self.settings.max_retries):
            try:
                r = self._client.post(url, json=payload, headers=headers)
                if r.status_code >= 500 or r.status_code == 429:
                    raise LLMError(f"upstream {r.status_code}: {r.text[:200]}")
                r.raise_for_status()
                data = r.json()
                choice = data["choices"][0]
                content = self._extract_openai_message_content(choice.get("message") or {})
                return LLMResponse(
                    content=content,
                    model=data.get("model", self.settings.model),
                    usage=data.get("usage", {}),
                    raw=data,
                    finish_reason=choice.get("finish_reason"),
                )
            except (httpx.HTTPError, LLMError) as e:
                last_err = e
                wait = min(2 ** attempt, 8)
                log.warning("LLM retry %s/%s after %ss: %s", attempt + 1, self.settings.max_retries, wait, e)
                time.sleep(wait)
        raise LLMError(f"LLM call failed after {self.settings.max_retries} attempts: {last_err}")

    def _chat_anthropic(
        self,
        messages: List[LLMMessage],
        temperature: float,
        max_tokens: Optional[int],
    ) -> LLMResponse:
        # 占位：实际接入时使用 anthropic-sdk
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.settings.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        system = next((m.content for m in messages if m.role == "system"), None)
        user_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        payload = {
            "model": self.settings.model,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
            "system": system or "",
            "messages": user_msgs,
        }
        r = self._client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        content = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        return LLMResponse(content=content, model=data.get("model", self.settings.model), usage=data.get("usage", {}), raw=data)

    def _ensure_api_key(self) -> None:
        if not (self.settings.api_key or "").strip():
            raise LLMError(
                "API Key 未设置。请在 App「设置」面板填写 API Key，然后点击「重启 sidecar」。"
            )

    def _msg_to_dict(self, m: LLMMessage) -> Dict[str, str]:
        return {"role": m.role, "content": m.content}

    def _extract_openai_message_content(self, message: Dict[str, Any]) -> str:
        """从 OpenAI 兼容响应里提取 assistant 正文。

        推理/思考模型（如 GLM）可能返回 content 为空：
        - content=null 且 reasoning_content 非空：典型"只思考不出正文"
        - content=""（空字符串）且 reasoning_content 非空：同上,但 content 字段类型是 str
        - 两者都为空：真正的空响应

        三种情况都应该 raise,让上层用 LLMError 转 502 暴露给前端,而不是静默返回空字符串
        ——后者会让续写/规划在 UI 上显示空白,但 status=200,排查极痛苦。
        """
        raw = message.get("content")
        reasoning = (message.get("reasoning_content") or "").strip()

        def _raise_empty() -> "str":
            # 推理链非空 → 配额被吃光;否则 → 真正的空响应
            if reasoning:
                raise LLMError(
                    "模型返回空正文：推理链占满输出配额（常见于推理/思考模型）。"
                    "请换用非推理模型（如 deepseek-chat），或增大 max_tokens / 换模型。"
                )
            raise LLMError(
                "模型返回空正文（content 与 reasoning_content 都为空）。"
                "通常是上游 502/超时后重试退化为空体，请稍后重试或换模型。"
            )

        if raw is None:
            return _raise_empty()
        if isinstance(raw, str):
            if not raw.strip():
                return _raise_empty()
            return raw
        if isinstance(raw, list):
            parts: list[str] = []
            for block in raw:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("content")
                    if text:
                        parts.append(str(text))
            joined = "".join(parts)
            if not joined.strip():
                return _raise_empty()
            return joined
        # 兜底:非 str/list/None 的 content(如 bool/int)不太可能出现
        coerced = str(raw)
        if not coerced.strip():
            return _raise_empty()
        return coerced

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """宽容 JSON 解析：兼容 ```json ... ``` 围栏。"""
        s = text.strip()
        if s.startswith("```"):
            # 去掉代码块围栏
            lines = s.splitlines()
            s = "\n".join(l for l in lines if not l.strip().startswith("```"))
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            raise LLMError(f"failed to parse JSON: {e}\nraw: {text[:300]}") from e

    def close(self) -> None:
        self._client.close()
