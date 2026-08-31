"""导入测试。覆盖 PRD F1/F2。"""
import pytest

from nextchapter_core.ingest import import_paste

pytestmark = pytest.mark.unit


def test_paste_basic():
    text = """
《九天神皇》
作者：墨羽青鸾

第一章 初入宗门
少年林尘踏入天玄宗...

第二章 试炼
第二轮试炼开始...
"""
    res = import_paste(text)
    assert res.title == "九天神皇"
    assert res.author == "墨羽青鸾"
    assert res.char_count > 0
    assert "林尘" in res.raw_text


def test_paste_no_metadata():
    text = "第一章 X\n内容..."
    res = import_paste(text)
    assert res.title == "未命名作品"
    assert res.author == ""
