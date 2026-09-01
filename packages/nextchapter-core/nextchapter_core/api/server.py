"""FastAPI sidecar：暴露给 Swift macOS app 调用。"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from .. import __version__
from ..config import load_settings
from ..llm import LLMClient, LLMError
from ..ingest import import_text, import_paste
from ..chunker import ChapterChunker
from ..summarize import Summarizer, SummaryTier, ChapterSummary
from ..context import ContextWindow
from ..style import StyleProfiler
from ..writing import ContinueEngine, ContinueMode, PlanningTurn
from ..consistency import ConsistencyChecker
from ..jobs import AnalyzeQueue

log = logging.getLogger("nextchapter.api")

# Swift app 启动时会校验此列表；旧 sidecar 缺少条目会被自动重启
API_FEATURES = ("plan_draft", "plan_revise", "critique", "analyze_async")


# ---- 应用 & 启动 ----

settings = load_settings()
llm = LLMClient(settings.llm)
chunker = ChapterChunker()
summarizer = Summarizer(llm)
context_window = ContextWindow(settings.context)
style_profiler = StyleProfiler(llm, settings.style)
continue_engine = ContinueEngine(llm)
checker = ConsistencyChecker(llm)
analyze_queue = AnalyzeQueue(summarizer, style_profiler)

app = FastAPI(title="NextChapter Core", version=__version__)


@app.exception_handler(LLMError)
def handle_llm_error(_request, exc: LLMError):
    """LLM 调用失败时返回可读错误，避免裸 500。"""
    log.warning("LLM error: %s", exc)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "features": list(API_FEATURES),
        "pid": __import__("os").getpid(),
        "started_at": int(time.time()),
        "llm_provider": settings.llm.provider,
        "llm_model": settings.llm.model,
        "llm_configured": bool((settings.llm.api_key or "").strip()),
    }


@app.post("/llm/ping")
def llm_ping() -> dict:
    """真实调用 LLM，验证 Key / 模型 / 网络是否可用。"""
    resp = llm.chat(
        [LLMMessage("user", "请只回复 OK 两个字母，不要其它内容。")],
        temperature=0,
        max_tokens=16,
    )
    return {
        "ok": True,
        "model": settings.llm.model,
        "provider": settings.llm.provider,
        "reply": (resp.content or "").strip()[:80],
    }


# ---- 数据模型（API DTO） ----


class ImportFromPathRequest(BaseModel):
    path: str


class ImportFromPasteRequest(BaseModel):
    text: str
    title: str = "未命名作品"
    author: str = ""


class ChapterDTO(BaseModel):
    index: int
    title: str
    body: str
    char_count: int
    kind: str


class ChapterListResponse(BaseModel):
    book_title: str
    author: str
    char_count: int
    chapters: List[ChapterDTO]


class SummarizeRequest(BaseModel):
    book_title: str
    chapters: List[ChapterDTO]
    # fine | coarse | ultra | all
    # "all" = 一次生成 fine+coarse+ultra（coarse/ultra 从 fine 派生，省 token）
    tier: str = "fine"
    indices: Optional[List[int]] = None  # None = 全部


class SummaryDTO(BaseModel):
    chapter_index: int
    title: str
    tier: str
    text: str


class SummarizeResponse(BaseModel):
    summaries: List[SummaryDTO]


class AnalyzeRequest(BaseModel):
    """一次完成：风格抽取 + 三档摘要（fine/coarse/ultra）。"""
    book_title: str
    chapters: List[ChapterDTO]
    # 只对新加的 chapters 做摘要；None = 全部重新生成
    indices: Optional[List[int]] = None
    # 增量摘要时传入已有 fine 摘要，供滚动上下文
    existing_summaries: Optional[List[SummaryDTO]] = None


class AnalyzeResponse(BaseModel):
    style_description: str
    anti_ai_directive: str
    style_samples: List[str]
    summaries: List[SummaryDTO]  # 三档混在一起，前端按 tier 字段筛选


class AnalyzeStartResponse(BaseModel):
    job_id: str
    style_description: str
    anti_ai_directive: str
    style_samples: List[str]
    total: int
    pending: int


class StyleRequest(BaseModel):
    book_title: str
    samples: List[ChapterDTO]


class StyleResponse(BaseModel):
    description: str
    anti_ai_directive: str
    samples: List[str]


class ContextRequest(BaseModel):
    summaries: List[SummaryDTO]
    total_chapters: int


class ContextResponse(BaseModel):
    rendered: str
    fine_count: int
    coarse_count: int
    ultra_count: int


class PlanningTurnDTO(BaseModel):
    role: str
    content: str


class PlanTurnRequest(BaseModel):
    book_title: str
    next_chapter_hint: str
    user_message: str
    history: List[PlanningTurnDTO] = Field(default_factory=list)
    context_text: str = ""
    style_text: str = ""


class PlanTurnResponse(BaseModel):
    assistant: str


class PlanDraftRequest(BaseModel):
    book_title: str
    next_chapter_hint: str
    context_text: str = ""
    style_text: str = ""


class PlanReviseRequest(BaseModel):
    book_title: str
    next_chapter_hint: str
    current_plan: str
    user_feedback: str
    history: List[PlanningTurnDTO] = Field(default_factory=list)
    context_text: str = ""
    style_text: str = ""


class ContinueRequest(BaseModel):
    book_title: str
    next_chapter_hint: str
    target_chars: int = 2000
    # PRD F10：续写动线
    # - "auto"      A 动线·一键续写（final_plan 必须为空）
    # - "user_plan" B 动线·用户规划续写（final_plan 必填，源自用户输入）
    # - "ai_plan"   C 动线·AI 规划续写（final_plan 必填，源自 plan_turn 讨论）
    mode: Literal["auto", "user_plan", "ai_plan"] = "auto"
    final_plan: str = ""
    history: List[PlanningTurnDTO] = Field(default_factory=list)
    context_text: str = ""
    style_text: str = ""

    @model_validator(mode="after")
    def _validate_mode_vs_final_plan(self):
        plan = (self.final_plan or "").strip()
        if self.mode == "auto":
            if plan:
                raise ValueError(
                    "mode=auto 时 final_plan 必须为空（一键续写不规划）。"
                    "如要按规划写，请改 mode=user_plan 或 ai_plan。"
                )
        else:  # user_plan / ai_plan
            if not plan:
                raise ValueError(
                    f"mode={self.mode} 时 final_plan 必填。"
                    "B 动线请把用户填的规划放进 final_plan；"
                    "C 动线请先调用 /continue/plan_turn 多轮讨论后锁定规划再传 final_plan。"
                )
        return self


class ContinueResponse(BaseModel):
    chapter_title: str
    body: str
    char_count: int
    # "stop" 表示自然结束；"length" 表示仍被 max_tokens 截断（已尝试自动续写）
    finish_reason: str = "stop"


class ConsistencyRequest(BaseModel):
    known_context: str
    new_chapter: str


class ConsistencyResponse(BaseModel):
    is_clean: bool
    summary: str
    issues: List[dict]


class CritiqueRequest(BaseModel):
    book_title: str
    next_chapter_hint: str
    target_chars: int = 2000
    mode: Literal["auto", "user_plan", "ai_plan"] = "auto"
    final_plan: str = ""
    history: List[PlanningTurnDTO] = Field(default_factory=list)
    context_text: str = ""
    style_text: str = ""
    # 当前草稿
    current_title: str = ""
    current_draft: str

    @model_validator(mode="after")
    def _validate_mode_vs_final_plan(self):
        plan = (self.final_plan or "").strip()
        if self.mode == "auto":
            if plan:
                raise ValueError(
                    "mode=auto 时 final_plan 必须为空。"
                    "如要按规划改写，请改 mode=user_plan 或 ai_plan。"
                )
        else:
            if not plan:
                raise ValueError(
                    f"mode={self.mode} 时 final_plan 必填。"
                )
        return self


class CritiqueIssueDTO(BaseModel):
    category: str
    severity: str
    description: str
    suggestion: str
    evidence: str = ""


class CritiqueResponse(BaseModel):
    summary: str
    issues: List[CritiqueIssueDTO]
    revised_title: str
    revised_body: str
    char_count: int


# ---- 端点 ----


@app.post("/ingest/path", response_model=ChapterListResponse)
def ingest_path(req: ImportFromPathRequest) -> ChapterListResponse:
    p = Path(req.path)
    if not p.exists():
        raise HTTPException(404, f"file not found: {req.path}")
    res = import_text(p)
    chapters = chunker.split(res.raw_text)
    return ChapterListResponse(
        book_title=res.title,
        author=res.author,
        char_count=res.char_count,
        chapters=[_ch_to_dto(c) for c in chapters],
    )


@app.post("/ingest/paste", response_model=ChapterListResponse)
def ingest_paste(req: ImportFromPasteRequest) -> ChapterListResponse:
    # 把空字符串视作「未指定」，让 import_paste 的 fallback 生效
    title = req.title.strip() or "未命名作品"
    res = import_paste(req.text, title=title, author=req.author)
    chapters = chunker.split(res.raw_text)
    return ChapterListResponse(
        book_title=res.title,
        author=res.author,
        char_count=res.char_count,
        chapters=[_ch_to_dto(c) for c in chapters],
    )


@app.post("/summarize", response_model=SummarizeResponse)
def summarize(req: SummarizeRequest) -> SummarizeResponse:
    from ..chunker import Chapter
    chs = [Chapter(index=c.index, title=c.title, body=c.body, kind=c.kind) for c in req.chapters]
    if req.indices is not None:
        chs = [c for c in chs if c.index in set(req.indices)]

    if req.tier == "all":
        # 一次生成 fine + coarse + ultra（后两者从 fine 派生，省 token）
        results = summarizer.summarize_all_tiers(chs)
    else:
        try:
            tier = SummaryTier(req.tier)
        except ValueError:
            raise HTTPException(400, f"invalid tier: {req.tier}")
        results = summarizer.summarize_all(chs, tier)

    return SummarizeResponse(
        summaries=[SummaryDTO(chapter_index=s.chapter_index, title=s.title, tier=s.tier.value, text=s.text) for s in results],
    )


@app.post("/style", response_model=StyleResponse)
def style(req: StyleRequest) -> StyleResponse:
    from ..chunker import Chapter
    chs = [Chapter(index=c.index, title=c.title, body=c.body, kind=c.kind) for c in req.samples]
    profile = style_profiler.profile(chs)
    return StyleResponse(
        description=profile.description,
        anti_ai_directive=profile.anti_ai_directive,
        samples=profile.samples,
    )


@app.post("/context/build", response_model=ContextResponse)
def context_build(req: ContextRequest) -> ContextResponse:
    from ..summarize import ChapterSummary
    sums = [ChapterSummary(chapter_index=s.chapter_index, title=s.title, tier=SummaryTier(s.tier), text=s.text) for s in req.summaries]
    wc = context_window.build(sums)
    # 用零层 summary 占位时，total_chapters 由调用方提供
    wc.total_chapters = req.total_chapters or wc.total_chapters
    return ContextResponse(
        rendered=wc.render_for_prompt(),
        fine_count=len(wc.fine),
        coarse_count=len(wc.coarse),
        ultra_count=len(wc.ultra),
    )


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """同步分析（短书/测试用）。长书请用 /analyze/start + SSE。"""
    from ..chunker import Chapter
    chs = [Chapter(index=c.index, title=c.title, body=c.body, kind=c.kind) for c in req.chapters]
    if not chs:
        raise HTTPException(400, "chapters 为空，无法分析")

    style_sample = chs[: settings.style.few_shot_chapters]
    profile = style_profiler.profile(style_sample)

    prior_fine = _seed_prior_fine(req.existing_summaries)
    if req.indices is not None:
        target = sorted(
            [c for c in chs if c.index in set(req.indices)],
            key=lambda c: c.index,
        )
        if not target:
            raise HTTPException(400, "indices 过滤后无章节")
        results = summarizer.summarize_all_tiers(target, prior_fine=prior_fine)
    else:
        results = summarizer.summarize_all_tiers(chs)

    return AnalyzeResponse(
        style_description=profile.description,
        anti_ai_directive=profile.anti_ai_directive,
        style_samples=profile.samples,
        summaries=[SummaryDTO(chapter_index=s.chapter_index, title=s.title, tier=s.tier.value, text=s.text) for s in results],
    )


@app.post("/analyze/start", response_model=AnalyzeStartResponse)
def analyze_start(req: AnalyzeRequest) -> AnalyzeStartResponse:
    """后台逐章摘要（对齐 Lumina）：立即返回 job_id，进度经 SSE 推送。"""
    from ..chunker import Chapter
    chs = [Chapter(index=c.index, title=c.title, body=c.body, kind=c.kind) for c in req.chapters]
    if not chs:
        raise HTTPException(400, "chapters 为空，无法分析")
    try:
        job = analyze_queue.start(
            req.book_title,
            chs,
            req.indices,
            extract_style=True,
            prior_fine=_seed_prior_fine(req.existing_summaries),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return AnalyzeStartResponse(
        job_id=job.job_id,
        style_description=job.style_description,
        anti_ai_directive=job.anti_ai_directive,
        style_samples=job.style_samples,
        total=job.total_count,
        pending=job.total_count,
    )


@app.get("/analyze/events/{job_id}")
def analyze_events(job_id: str) -> StreamingResponse:
    """SSE：chapter_ready / analyze_progress / analyze_done / analyze_error / analyze_cancelled。"""
    if analyze_queue.get_job(job_id) is None:
        raise HTTPException(404, f"job not found: {job_id}")
    return StreamingResponse(
        analyze_queue.iter_events(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/analyze/cancel/{job_id}")
def analyze_cancel(job_id: str) -> dict:
    """停止后台摘要：当前章完成后终止，已完成的章节摘要保留。"""
    if not analyze_queue.cancel(job_id):
        job = analyze_queue.get_job(job_id)
        if job is None:
            raise HTTPException(404, f"job not found: {job_id}")
        raise HTTPException(409, f"job already {job.status}")
    return {"ok": True, "job_id": job_id}


def _seed_prior_fine(existing: Optional[List[SummaryDTO]]) -> List[ChapterSummary]:
    if not existing:
        return []
    fine = [
        ChapterSummary(
            chapter_index=s.chapter_index,
            title=s.title,
            tier=SummaryTier.FINE,
            text=s.text,
        )
        for s in existing
        if s.tier == "fine"
    ]
    fine.sort(key=lambda x: x.chapter_index)
    return fine


@app.post("/continue/plan_turn", response_model=PlanTurnResponse)
def continue_plan_turn(req: PlanTurnRequest) -> PlanTurnResponse:
    from ..writing import ContinueRequest
    history = [PlanningTurn(role=t.role, content=t.content) for t in req.history]
    fake_style = _fake_style_profile(req.style_text)
    fake_ctx = _fake_windowed_context(req.context_text)
    cr = ContinueRequest(
        book_title=req.book_title,
        next_chapter_hint=req.next_chapter_hint,
        planning_history=history,
        style=fake_style,
        context=fake_ctx,
    )
    turn = continue_engine.plan_turn(cr, req.user_message)
    return PlanTurnResponse(assistant=turn.content)


@app.post("/continue/plan_draft", response_model=PlanTurnResponse)
def continue_plan_draft(req: PlanDraftRequest) -> PlanTurnResponse:
    """C 动线：一键生成规划初稿（5 维极简纲要，硬性 ≤200 字）。"""
    from ..writing import ContinueRequest
    fake_style = _fake_style_profile(req.style_text)
    fake_ctx = _fake_windowed_context(req.context_text)
    cr = ContinueRequest(
        book_title=req.book_title,
        next_chapter_hint=req.next_chapter_hint,
        style=fake_style,
        context=fake_ctx,
    )
    turn = continue_engine.plan_draft(cr)
    return PlanTurnResponse(assistant=turn.content)


@app.post("/continue/plan_revise", response_model=PlanTurnResponse)
def continue_plan_revise(req: PlanReviseRequest) -> PlanTurnResponse:
    """C 动线：根据用户反馈直接重写规划（自动覆盖初稿）。"""
    from ..writing import ContinueRequest
    if not req.user_feedback.strip():
        raise HTTPException(400, "user_feedback 不能为空。")
    history = [PlanningTurn(role=t.role, content=t.content) for t in req.history]
    fake_style = _fake_style_profile(req.style_text)
    fake_ctx = _fake_windowed_context(req.context_text)
    cr = ContinueRequest(
        book_title=req.book_title,
        next_chapter_hint=req.next_chapter_hint,
        planning_history=history,
        style=fake_style,
        context=fake_ctx,
    )
    turn = continue_engine.plan_revise(cr, req.current_plan, req.user_feedback)
    return PlanTurnResponse(assistant=turn.content)


@app.post("/continue/generate", response_model=ContinueResponse)
def continue_generate(req: ContinueRequest) -> ContinueResponse:
    from ..writing import ContinueRequest
    history = [PlanningTurn(role=t.role, content=t.content) for t in req.history]
    fake_style = _fake_style_profile(req.style_text)
    fake_ctx = _fake_windowed_context(req.context_text)
    cr = ContinueRequest(
        book_title=req.book_title,
        next_chapter_hint=req.next_chapter_hint,
        target_chars=req.target_chars,
        mode=ContinueMode(req.mode),
        final_plan=req.final_plan,
        planning_history=history,
        style=fake_style,
        context=fake_ctx,
    )
    result = continue_engine.generate(cr)
    return ContinueResponse(
        chapter_title=result.chapter_title,
        body=result.body,
        char_count=result.char_count,
        finish_reason=result.finish_reason,
    )


@app.post("/consistency/check", response_model=ConsistencyResponse)
def consistency_check(req: ConsistencyRequest) -> ConsistencyResponse:
    r = checker.check(req.known_context, req.new_chapter)
    return ConsistencyResponse(is_clean=r.is_clean, summary=r.summary, issues=[
        {
            "category": i.category,
            "field": i.field,
            "description": i.description,
            "severity": i.severity,
            "evidence": i.evidence,
        }
        for i in r.issues
    ])


@app.post("/continue/critique", response_model=CritiqueResponse)
def continue_critique(req: CritiqueRequest) -> CritiqueResponse:
    """对已生成的草稿做审稿 + 改写。

    输出一份修改意见（结构化 issues）+ 一份建议重写版正文。
    """
    from ..writing import ContinueRequest
    if not req.current_draft.strip():
        raise HTTPException(400, "current_draft 不能为空：先生成草稿再请求 AI 重写。")

    history = [PlanningTurn(role=t.role, content=t.content) for t in req.history]
    fake_style = _fake_style_profile(req.style_text)
    fake_ctx = _fake_windowed_context(req.context_text)
    cr = ContinueRequest(
        book_title=req.book_title,
        next_chapter_hint=req.next_chapter_hint,
        target_chars=req.target_chars,
        mode=ContinueMode(req.mode),
        final_plan=req.final_plan,
        planning_history=history,
        style=fake_style,
        context=fake_ctx,
    )
    try:
        result = continue_engine.critique(
            cr,
            current_draft=req.current_draft,
            current_title=req.current_title,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return CritiqueResponse(
        summary=result.summary,
        issues=[
            CritiqueIssueDTO(
                category=i.category,
                severity=i.severity,
                description=i.description,
                suggestion=i.suggestion,
                evidence=i.evidence,
            )
            for i in result.issues
        ],
        revised_title=result.revised_title,
        revised_body=result.revised_body,
        char_count=len(result.revised_body),
    )


# ---- helpers ----


def _ch_to_dto(c) -> ChapterDTO:
    return ChapterDTO(index=c.index, title=c.title, body=c.body, char_count=c.char_count, kind=c.kind)


def _fake_style_profile(text: str):
    from ..style import StyleProfile
    return StyleProfile(samples=[], description=text, anti_ai_directive="")


def _fake_windowed_context(text: str):
    from ..context import WindowedContext
    return WindowedContext(
        fine=[], coarse=[], ultra=[], total_chapters=0,
        rendered_override=text or "",
    )


def run() -> None:
    """启动 sidecar HTTP 服务。"""
    import uvicorn
    uvicorn.run(
        "nextchapter_core.api.server:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    run()
