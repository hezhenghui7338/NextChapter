"""中文章节切分：识别「第X章」「卷」「序」等结构。"""
from .chunker import ChapterChunker, Chapter

__all__ = ["ChapterChunker", "Chapter"]
