"""端到端 demo：导入示例网文 → 跑完整流程 → 打印每步结果。

不需要真实 LLM：用 mock client 演示整个流水线。
直接跑：python3 scripts/demo_flow.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 让 `from nextchapter_core.xxx` 可用
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nextchapter_core.ingest import import_paste
from nextchapter_core.chunker import ChapterChunker
from nextchapter_core.summarize import Summarizer, SummaryTier
from nextchapter_core.context import ContextWindow
from nextchapter_core.style import StyleProfiler
from nextchapter_core.writing import ContinueEngine, ContinueRequest, PlanningTurn
from nextchapter_core.consistency import ConsistencyChecker
from nextchapter_core.config import load_settings
from tests.support.mock_llm import MockLLMClient
from tests.support.summary_builder import (
    build_mock_summaries,
    build_mock_style,
    build_mock_continuation,
    build_mock_consistency_issues,
)


def main() -> None:
    settings = load_settings()
    llm = MockLLMClient()

    # 1) 导入示例
    sample = ROOT / "tests" / "fixtures" / "books" / "sample_novel.txt"
    text = sample.read_text(encoding="utf-8")
    print(f"\n[1/6] 导入示例网文：{sample.name}")
    res = import_paste(text)
    print(f"      书名：{res.title}    作者：{res.author}    字数：{res.char_count}")

    # 2) 章节切分
    chunker = ChapterChunker()
    chapters = chunker.split(res.raw_text)
    print(f"\n[2/6] 章节切分：{len(chapters)} 章")
    for c in chapters:
        print(f"      · {c.title}  ({c.char_count} 字)")

    # 3) 风格抽取
    print(f"\n[3/6] 风格向量抽取（mock LLM）...")
    llm.set_callback(build_mock_style)
    style_profiler = StyleProfiler(llm, settings.style)
    style = style_profiler.profile(chapters)
    print(f"      反 AI 味：{style.anti_ai_directive.splitlines()[0]}...")
    print(f"      样本数：{len(style.samples)}")

    # 4) 三档摘要
    print(f"\n[4/6] 三档摘要（mock LLM）...")
    summarizer = Summarizer(llm)
    n = len(chapters)
    llm.set_callback(lambda m, kw: build_mock_summaries(m, kw, n, "fine"))
    fine = summarizer.summarize_all(chapters, SummaryTier.FINE)
    print(f"      fine (400字目标): {len(fine)} 段")
    for s in fine[:3]:
        print(f"        · {s.title}：{s.text[:60]}...")

    # 5) 上下文窗口 + 规划讨论 + 一键续写
    print(f"\n[5/6] 上下文窗口 + 规划讨论 + 一键续写")
    ctx_window = ContextWindow(settings.context)
    ctx = ctx_window.build(fine)
    print(f"      窗口：fine={len(ctx.fine)} / coarse={len(ctx.coarse)} / ultra={len(ctx.ultra)}")

    llm.set_callback(lambda m, kw: "建议先设计爽点：身份暴露。")
    engine = ContinueEngine(llm)
    plan_turn = engine.plan_turn(
        ContinueRequest(
            book_title=res.title,
            next_chapter_hint="第 8 章",
            planning_history=[],
            context=ctx,
            style=style,
        ),
        user_message="第 8 章要怎么写？",
    )
    print(f"      规划讨论 AI 回复：{plan_turn.content[:80]}")

    llm.set_callback(lambda m, kw: build_mock_continuation(m, kw, "第八章 身份暴露"))
    chapter = engine.generate(
        ContinueRequest(
            book_title=res.title,
            next_chapter_hint="第 8 章",
            target_chars=2000,
            final_plan="主角身份暴露，三招两式击败埋伏的敌人",
            planning_history=[PlanningTurn(role="user", content="..."), PlanningTurn(role="assistant", content=plan_turn.content)],
            context=ctx,
            style=style,
        )
    )
    print(f"      生成章节：{chapter.chapter_title}  ({chapter.char_count} 字)")
    print(f"      正文前 80 字：{chapter.body[:80]}...")

    # 6) 一致性检查
    print(f"\n[6/6] 一致性检查（mock LLM）...")
    llm.set_callback(lambda m, kw: build_mock_consistency_issues())
    checker = ConsistencyChecker(llm)
    check = checker.check(ctx.render_for_prompt(), chapter.chapter_title + "\n\n" + chapter.body)
    print(f"      总结：{check.summary}")
    print(f"      发现冲突：{len(check.issues)}")
    for issue in check.issues:
        print(f"        ⚠️  [{issue.severity}] {issue.category}/{issue.field}: {issue.description[:60]}")

    print("\n✅ Demo 跑完。真实使用时把 MockLLMClient 换成 LLMClient(settings.llm) 即可。\n")


if __name__ == "__main__":
    main()
