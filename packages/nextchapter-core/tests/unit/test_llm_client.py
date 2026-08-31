"""LLM 客户端测试。覆盖 PRD 4.3：OpenAI 兼容 + Anthropic + 重试 + JSON 解析。"""
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from nextchapter_core.config import LLMSettings
from nextchapter_core.llm import LLMClient, LLMMessage

pytestmark = pytest.mark.unit


def _make_response(status: int, payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.text = json.dumps(payload)
    resp.raise_for_status = MagicMock()
    return resp


def test_chat_openai_compat_basic():
    settings = LLMSettings(provider="openai", api_key="sk-test", base_url="https://api.openai.com/v1", model="gpt-4o")
    client = LLMClient(settings)
    payload = {
        "id": "x", "model": "gpt-4o",
        "choices": [{"message": {"role": "assistant", "content": "你好"}}],
        "usage": {"total_tokens": 10},
    }
    with patch.object(client._client, "post", return_value=_make_response(200, payload)) as mock_post:
        resp = client.chat([LLMMessage("user", "hi")])
    assert resp.content == "你好"
    assert resp.model == "gpt-4o"
    assert resp.usage["total_tokens"] == 10
    # 确认 URL 和 headers
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.openai.com/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"


def test_chat_json_force_response_format():
    settings = LLMSettings(provider="openai", api_key="k", base_url="https://x", model="m")
    client = LLMClient(settings)
    payload = {"choices": [{"message": {"content": '{"a": 1}'}}]}
    with patch.object(client._client, "post", return_value=_make_response(200, payload)) as mock_post:
        out = client.chat_json([LLMMessage("user", "go json")])
    assert out == {"a": 1}
    kwargs = mock_post.call_args.kwargs
    assert kwargs["json"]["response_format"] == {"type": "json_object"}


def test_retry_on_5xx():
    settings = LLMSettings(provider="openai", api_key="k", base_url="https://x", model="m", max_retries=2, timeout=1)
    client = LLMClient(settings)
    # 第一次 5xx 失败，第二次成功
    success = _make_response(200, {"choices": [{"message": {"content": "ok"}}]})
    fail = _make_response(500, {"err": "boom"})
    with patch.object(client._client, "post", side_effect=[fail, success]) as mock_post:
        resp = client.chat([LLMMessage("user", "hi")])
    assert resp.content == "ok"
    assert mock_post.call_count == 2


def test_retry_gives_up():
    settings = LLMSettings(provider="openai", api_key="k", base_url="https://x", model="m", max_retries=2, timeout=1)
    client = LLMClient(settings)
    fail = _make_response(500, {"err": "boom"})
    with patch.object(client._client, "post", return_value=fail):
        from nextchapter_core.llm.client import LLMError
        with pytest.raises(LLMError):
            client.chat([LLMMessage("user", "hi")])


def test_null_content_with_reasoning_raises():
    """推理模型 content=null 时应给出可读错误，而非 AttributeError。"""
    settings = LLMSettings(provider="openai", api_key="k", base_url="https://x", model="m")
    client = LLMClient(settings)
    payload = {
        "choices": [{
            "message": {"role": "assistant", "content": None, "reasoning_content": "思考中…"},
            "finish_reason": "length",
        }],
    }
    with patch.object(client._client, "post", return_value=_make_response(200, payload)):
        from nextchapter_core.llm.client import LLMError
        with pytest.raises(LLMError, match="空正文"):
            client.chat([LLMMessage("user", "hi")])


def test_null_content_without_reasoning_returns_empty():
    settings = LLMSettings(provider="openai", api_key="k", base_url="https://x", model="m")
    client = LLMClient(settings)
    payload = {"choices": [{"message": {"role": "assistant", "content": None}}]}
    with patch.object(client._client, "post", return_value=_make_response(200, payload)):
        resp = client.chat([LLMMessage("user", "hi")])
    assert resp.content == ""


def test_empty_api_key_raises_before_http():
    settings = LLMSettings(provider="openai", api_key="", base_url="https://x", model="m")
    client = LLMClient(settings)
    from nextchapter_core.llm.client import LLMError
    with pytest.raises(LLMError, match="API Key"):
        client.chat([LLMMessage("user", "hi")])


def test_fake_windowed_context_uses_rendered_override():
    from nextchapter_core.api.server import _fake_windowed_context
    ctx = _fake_windowed_context("【近期剧情】\n· 第一章：测试")
    assert "第一章" in ctx.render_for_prompt()


def test_parse_json_strips_fence():
    settings = LLMSettings(provider="openai", api_key="k", base_url="https://x", model="m")
    client = LLMClient(settings)
    out = client._parse_json('```json\n{"a": 1}\n```')
    assert out == {"a": 1}


def test_parse_json_raises_on_garbage():
    settings = LLMSettings(provider="openai", api_key="k", base_url="https://x", model="m")
    client = LLMClient(settings)
    from nextchapter_core.llm.client import LLMError
    with pytest.raises(LLMError):
        client._parse_json("not json")


def test_anthropic_path_uses_messages_api():
    settings = LLMSettings(provider="anthropic", api_key="ant-key", base_url="", model="claude-3-5-sonnet")
    client = LLMClient(settings)
    payload = {
        "model": "claude-3-5-sonnet",
        "content": [{"type": "text", "text": "你好"}],
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    with patch.object(client._client, "post", return_value=_make_response(200, payload)) as mock_post:
        resp = client.chat([
            LLMMessage("system", "你是助手"),
            LLMMessage("user", "你好"),
        ])
    assert resp.content == "你好"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.anthropic.com/v1/messages"
    assert kwargs["headers"]["x-api-key"] == "ant-key"
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    # system 应该被单独抽出来
    body = kwargs["json"]
    assert body["system"] == "你是助手"
    assert body["messages"] == [{"role": "user", "content": "你好"}]
