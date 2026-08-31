"""中文章节切分。

借鉴 Lumina 的 `chunker/` 思路，做网文特化：
- 「第X章」「第X回」「第XXX章」作为强信号
- 「卷X」「序」「序章」「楔子」「番外」作为软信号
- 装饰线 / 全大写标题兼容
- 短章节合并（<300 字 与相邻章节合并）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# 强章节信号：第X章 / 第X回
RE_CHAPTER = re.compile(
    r"^[ \t]*(?:"
    r"第[0-9零一二三四五六七八九十百千两壹贰叁肆伍陆柒捌玖拾佰仟]+[章回]"  # 第X章
    r"|Chapter\s+\d+"  # 英文 Chapter X
    r")\s*[:：、\. ]?.*$",
    re.MULTILINE,
)

# 软信号：卷/序/楔子/番外
RE_SOFT = re.compile(
    r"^[ \t]*(?:"
    r"第[0-9零一二三四五六七八九十百千两]+卷"  # 第X卷
    r"|序\s*章|序$|楔子|引子|后记|番外|外篇"  # 序/楔子等
    r")\s*[:：、\. ]?.*$",
    re.MULTILINE,
)


@dataclass
class Chapter:
    index: int
    title: str
    body: str
    char_count: int = 0
    kind: str = "chapter"  # chapter | volume | prelude | interlude | extra
    start_offset: int = 0
    end_offset: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.body)


class ChapterChunker:
    """切分中文网文为章节列表。

    用法：
        chunker = ChapterChunker()
        chapters = chunker.split(text)
    """

    MIN_CHAPTER_CHARS = 80   # 短章节合并阈值（< 此值视为噪声/意外中断，合并到上一章）

    def split(self, text: str) -> list[Chapter]:
        # 1. 找到所有强信号位置
        boundaries: list[tuple[int, str, str]] = []  # (offset, title, kind)
        for m in RE_CHAPTER.finditer(text):
            title = m.group(0).strip()
            kind = "chapter"
            boundaries.append((m.start(), title, kind))
        for m in RE_SOFT.finditer(text):
            title = m.group(0).strip()
            kind = self._classify_soft(title)
            boundaries.append((m.start(), title, kind))

        if not boundaries:
            # 没找到章节，整个作为一个"全文"章节
            return [Chapter(index=0, title="全文", body=text.strip(), kind="chapter")]

        # 2. 按 offset 排序、去重（强信号优先）
        boundaries.sort(key=lambda x: (x[0], 0 if x[2] == "chapter" else 1))
        unique: list[tuple[int, str, str]] = []
        for b in boundaries:
            if unique and b[0] - unique[-1][0] < 5:
                continue
            unique.append(b)

        # 3. 切出章节
        chapters: list[Chapter] = []
        for i, (offset, title, kind) in enumerate(unique):
            end = unique[i + 1][0] if i + 1 < len(unique) else len(text)
            body = text[offset:end].strip()
            chapters.append(
                Chapter(
                    index=len(chapters),
                    title=title,
                    body=body,
                    kind=kind,
                    start_offset=offset,
                    end_offset=end,
                )
            )

        # 4. 合并过短章节（与下一章合并）
        merged: list[Chapter] = []
        for ch in chapters:
            if merged and len(ch.body) < self.MIN_CHAPTER_CHARS and ch.kind == "chapter":
                # 拼到上一章
                last = merged[-1]
                last.body = (last.body + "\n\n" + ch.body).strip()
                last.char_count = len(last.body)
            else:
                merged.append(ch)

        # 5. 重新编号
        for i, ch in enumerate(merged):
            ch.index = i

        return merged

    def _classify_soft(self, title: str) -> str:
        t = title.lower()
        if "卷" in title and "章" not in title:
            return "volume"
        if "番外" in title or "外篇" in title:
            return "extra"
        if "后记" in title:
            return "afterword"
        return "prelude"
