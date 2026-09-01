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
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        self._ensure_api_key()
        if self.settings.provider == "anthropic":
            return self._chat_anthropic(messages, temperature, max_tokens, timeout=timeout)
        return self._chat_openai_compat(messages, temperature, max_tokens, response_format, timeout=timeout)

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
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        url = f"{self.settings.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.api_key}",
        }
        last_err: Optional[Exception] = None
        req_timeout = timeout if timeout is not None else self.settings.timeout
        base_payload: Dict[str, Any] = {
            "model": self.settings.model,
            "messages": [self._msg_to_dict(m) for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            base_payload["max_tokens"] = max_tokens
        if response_format == "json":
            base_payload["response_format"] = {"type": "json_object"}

        for attempt in range(self.settings.max_retries):
            payload = dict(base_payload)
            self._maybe_disable_thinking(payload, attempt=attempt)
            try:
                r = self._client.post(url, json=payload, headers=headers, timeout=req_timeout)
                if r.status_code == 400 and attempt == 0 and self._thinking_disabled_in(payload):
                    # 部分厂商不支持 thinking 开关字段，去掉后重试
                    payload = dict(base_payload)
                    r = self._client.post(url, json=payload, headers=headers, timeout=req_timeout)
                if r.status_code >= 500 or r.status_code == 429:
                    raise LLMError(f"upstream {r.status_code}: {r.text[:200]}")
                if r.status_code >= 400:
                    raise LLMError(f"upstream {r.status_code}: {r.text[:300]}")
                data = r.json()
                choices = data.get("choices") or []
                if not choices:
                    raise LLMError(
                        f"模型 [{self.settings.model}] 返回空 choices。"
                        f"raw: {json.dumps(data, ensure_ascii=False)[:300]}"
                    )
                choice = choices[0]
                content = self._extract_openai_message_content(
                    choice.get("message") or {}, choice=choice, raw=data,
                )
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
        timeout: Optional[float] = None,
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
        r = self._client.post(
            url, json=payload, headers=headers,
            timeout=timeout if timeout is not None else self.settings.timeout,
        )
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

    def _maybe_disable_thinking(self, payload: Dict[str, Any], *, attempt: int) -> None:
        """Flash / 推理模型常把 token 耗在 thinking 字段，导致 content 为空。"""
        import os
        flag = os.getenv("NC_LLM_DISABLE_THINKING", "auto").lower()
        if flag in {"0", "false", "no", "off"}:
            return
        model = (self.settings.model or "").lower()
        auto = any(h in model for h in ("flash", "reasoner", "thinking", "glm-5", "glm5", "qwq", "o1", "o3"))
        if flag not in {"1", "true", "yes", "on"} and not auto:
            return
        # 多厂商约定；不支持的 API 会在 400 时被上层去掉重试
        payload["enable_thinking"] = False
        payload.setdefault("thinking", {"type": "disabled"})
        payload.setdefault("chat_template_kwargs", {"enable_thinking": False})

    @staticmethod
    def _thinking_disabled_in(payload: Dict[str, Any]) -> bool:
        return "enable_thinking" in payload or "thinking" in payload

    def _extract_openai_message_content(
        self,
        message: Dict[str, Any],
        *,
        choice: Optional[Dict[str, Any]] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> str:
        """从 OpenAI 兼容响应里提取 assistant 正文。

        推理/思考模型（如 GLM）可能返回 content 为空：
        - content=null 且 reasoning_content 非空：典型"只思考不出正文"
        - content=""（空字符串）且 reasoning_content 非空：同上,但 content 字段类型是 str
        - 两者都为空：真正的空响应

        三种情况都应该 raise,让上层用 LLMError 转 502 暴露给前端,而不是静默返回空字符串
        ——后者会让续写/规划在 UI 上显示空白,但 status=200,排查极痛苦。
        """
        raw_content = message.get("content")
        reasoning = self._collect_reasoning_text(message, choice)

        model_hint = self.settings.model or "(unknown)"
        diag = self._empty_content_diag(message, choice, raw)

        def _raise_empty() -> "str":
            if reasoning:
                raise LLMError(
                    f"模型 [{model_hint}] 返回空正文：推理链占满输出配额（常见于 Flash/思考模型）。"
                    "已在请求里尝试关闭 thinking；若仍失败，请换 deepseek-chat 等非思考模型，"
                    "或设置 NC_LLM_DISABLE_THINKING=1 后重启 sidecar。"
                    f"{diag}"
                )
            raise LLMError(
                f"模型 [{model_hint}] 返回空正文（content 与 reasoning 都为空）。"
                f"请确认 sidecar 已重启、Base URL/模型名正确。{diag}"
            )

        # 部分 OpenAI 兼容 API 用 choice.text
        if choice:
            legacy = choice.get("text")
            if isinstance(legacy, str) and legacy.strip():
                return legacy.strip()

        if raw_content is None:
            return _raise_empty()
        if isinstance(raw_content, str):
            if not raw_content.strip():
                return _raise_empty()
            return raw_content
        if isinstance(raw_content, list):
            parts: list[str] = []
            for block in raw_content:
                if isinstance(block, dict):
                    btype = str(block.get("type") or "").lower()
                    if btype in {"thinking", "reasoning", "thought", "redacted_thinking"}:
                        continue
                    text = (
                        block.get("text")
                        or block.get("content")
                        or block.get("output_text")
                    )
                    if text:
                        parts.append(str(text))
                elif isinstance(block, str) and block.strip():
                    parts.append(block)
            joined = "".join(parts)
            if not joined.strip():
                return _raise_empty()
            return joined
        coerced = str(raw_content)
        if not coerced.strip():
            return _raise_empty()
        return coerced

    @staticmethod
    def _collect_reasoning_text(
        message: Dict[str, Any], choice: Optional[Dict[str, Any]] = None,
    ) -> str:
        chunks: list[str] = []
        sources = [message]
        if choice:
            msg = choice.get("message")
            if isinstance(msg, dict) and msg is not message:
                sources.append(msg)
            sources.append(choice)
        for src in sources:
            if not isinstance(src, dict):
                continue
            for key in ("reasoning_content", "reasoning", "thinking", "reasoning_text"):
                val = src.get(key)
                if val:
                    chunks.append(str(val).strip())
        return " ".join(chunks).strip()

    @staticmethod
    def _empty_content_diag(
        message: Dict[str, Any],
        choice: Optional[Dict[str, Any]],
        raw: Optional[Dict[str, Any]],
    ) -> str:
        keys: list[str] = []
        if isinstance(message, dict):
            keys.extend(list(message.keys()))
        if isinstance(choice, dict):
            keys.extend([f"choice.{k}" for k in choice.keys()])
        if keys:
            return f" 响应字段: {', '.join(sorted(set(keys))[:12])}。"
        return ""

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
