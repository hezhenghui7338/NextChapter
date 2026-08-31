"""Pytest 全局配置 + 共享 fixtures。"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

import httpx
import pytest

# 把项目根加进 sys.path（让 nextchapter_core 可被 import）
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
BOOKS_DIR = FIXTURES_DIR / "books"
LLM_DIR = FIXTURES_DIR / "llm"


# ---- 共享 fixtures ----


@pytest.fixture
def books_dir() -> Path:
    return BOOKS_DIR


@pytest.fixture
def llm_dir() -> Path:
    return LLM_DIR


@pytest.fixture
def sample_novel_text() -> str:
    return (BOOKS_DIR / "sample_novel.txt").read_text(encoding="utf-8")


@pytest.fixture
def short_novel_text() -> str:
    return (BOOKS_DIR / "short_novel.txt").read_text(encoding="utf-8")


@pytest.fixture
def no_chapter_text() -> str:
    return (BOOKS_DIR / "no_chapter.txt").read_text(encoding="utf-8")


@pytest.fixture
def sample_summaries() -> dict:
    return json.loads((LLM_DIR / "sample_summaries.json").read_text(encoding="utf-8"))


@pytest.fixture
def style_profile_json() -> dict:
    return json.loads((LLM_DIR / "style_profile.json").read_text(encoding="utf-8"))


@pytest.fixture
def consistency_issues() -> dict:
    return json.loads((LLM_DIR / "consistency_issues.json").read_text(encoding="utf-8"))


@pytest.fixture
def continuation_chapter() -> str:
    return (LLM_DIR / "continuation_chapter.txt").read_text(encoding="utf-8")


# ---- 端口检测：避免和 Lumina 冲突 ----


@pytest.fixture(scope="session")
def free_port() -> int:
    """找一个空闲端口，供 e2e 测试启动独立 sidecar。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---- 环境变量：保证默认配置可加载 ----


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """每个测试前清掉可能影响配置的 NC_* 环境变量。"""
    for k in list(os.environ):
        if k.startswith("NC_"):
            monkeypatch.delenv(k, raising=False)
    yield
