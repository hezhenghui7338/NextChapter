"""E2E 测试共享 fixtures：FastAPI app + Mock LLM + 测试客户端。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nextchapter_core.api import server as server_module
from nextchapter_core.config import LLMSettings
from nextchapter_core.llm import LLMClient, LLMMessage, LLMResponse
from tests.support.mock_llm import MockLLMClient


@pytest.fixture
def mock_llm() -> MockLLMClient:
    """统一 mock LLM，所有 e2e 测试都用这个。"""
    return MockLLMClient()


@pytest.fixture
def client(mock_llm: MockLLMClient, monkeypatch) -> TestClient:
    """注入 mock LLM 的 FastAPI TestClient。"""
    # 把 server 模块里的全局 llm 替换为 mock
    monkeypatch.setattr(server_module, "llm", mock_llm)
    # 重建依赖 mock 的服务实例
    from nextchapter_core.summarize import Summarizer
    from nextchapter_core.style import StyleProfiler
    from nextchapter_core.writing import ContinueEngine
    from nextchapter_core.consistency import ConsistencyChecker

    monkeypatch.setattr(server_module, "summarizer", Summarizer(mock_llm))
    monkeypatch.setattr(server_module, "style_profiler", StyleProfiler(mock_llm, server_module.settings.style))
    monkeypatch.setattr(server_module, "continue_engine", ContinueEngine(mock_llm))
    monkeypatch.setattr(server_module, "checker", ConsistencyChecker(mock_llm))

    return TestClient(server_module.app)
