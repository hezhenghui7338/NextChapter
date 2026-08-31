"""配置加载测试。"""
import pytest

from nextchapter_core.config import (
    ContextSettings,
    LLMSettings,
    StyleSettings,
    load_settings,
)

pytestmark = pytest.mark.unit


def test_default_context_window():
    s = ContextSettings()
    assert s.recent_chapter_count == 5
    assert s.middle_chapter_count == 10
    assert s.far_chapter_count == 10
    assert s.fine_summary_chars == 400
    assert s.coarse_summary_chars == 150
    assert s.ultra_summary_chars == 60


def test_default_style_settings():
    s = StyleSettings()
    assert s.few_shot_chapters == 3
    assert s.anti_ai_preset == "default"


def test_llm_from_env(monkeypatch):
    monkeypatch.setenv("NC_LLM_PROVIDER", "openai")
    monkeypatch.setenv("NC_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("NC_LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("NC_LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("NC_LLM_TIMEOUT", "60")

    s = LLMSettings.from_env()
    assert s.provider == "openai"
    assert s.api_key == "sk-test"
    assert s.base_url == "https://api.openai.com/v1"
    assert s.model == "gpt-4o"
    assert s.timeout == 60.0


def test_load_settings_creates_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("NC_DATA_DIR", str(tmp_path / "ncdata"))
    s = load_settings()
    assert s.data_dir.exists()
    assert s.data_dir.is_dir()


def test_port_default():
    """Port 必须和 Lumina 错开，避免本地同时跑两个项目冲突。"""
    from nextchapter_core.config import DEFAULT_PORT
    assert DEFAULT_PORT == 18432
