"""TXT / 粘贴导入。

M1 只做 TXT（MVP 决策）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImportResult:
    title: str
    author: str
    raw_text: str
    char_count: int


def import_text(path: str | Path) -> ImportResult:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    title, author = _parse_title_author(text, fallback=p.stem)
    return ImportResult(title=title, author=author, raw_text=text, char_count=len(text))


def import_paste(text: str, title: str = "未命名作品", author: str = "") -> ImportResult:
    text = text.strip()
    parsed_title, parsed_author = _parse_title_author(text, fallback=title)
    return ImportResult(
        title=parsed_title or title,
        author=parsed_author or author,
        raw_text=text,
        char_count=len(text),
    )


def _parse_title_author(text: str, fallback: str) -> tuple[str, str]:
    """从开头几行粗略识别书名/作者。网文常见格式：
        《书名》
        作者：xxx
        ...
    """
    lines = [l.strip() for l in text.splitlines()[:20] if l.strip()]
    title = fallback
    author = ""
    for line in lines:
        # 书名
        if "《" in line and "》" in line:
            title = line[line.index("《") + 1 : line.index("》")] or title
        # 作者
        if "作者" in line and ("：" in line or ":" in line):
            sep = "：" if "：" in line else ":"
            author = line.split(sep, 1)[1].strip()
            break
    return title, author
