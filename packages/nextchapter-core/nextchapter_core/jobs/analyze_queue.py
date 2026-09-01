"""后台分析队列：分批并发摘要 + SSE 推送（对齐 Lumina JobQueue 思路）。"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, Dict, Iterator, List, Optional

from ..chunker import Chapter
from ..config import SUMMARY_CONCURRENCY
from ..style import StyleProfiler
from ..summarize import Summarizer

log = logging.getLogger("nextchapter.jobs.analyze")


@dataclass
class AnalyzeJob:
    job_id: str
    book_title: str
    chapters: List[Chapter]
    indices: List[int]
    style_description: str = ""
    anti_ai_directive: str = ""
    style_samples: List[str] = field(default_factory=list)
    status: str = "queued"  # queued | running | done | error | cancelled
    done_count: int = 0
    total_count: int = 0
    error: Optional[str] = None
    cancelled: bool = False
    prior_fine_seed: List[Any] = field(default_factory=list)
    event_log: List[dict] = field(default_factory=list)
    subscribers: List[Queue] = field(default_factory=list)


class AnalyzeQueue:
    """内存任务队列：按波次并发摘要（默认 8 路），结果经 SSE 推送。"""

    def __init__(self, summarizer: Summarizer, style_profiler: StyleProfiler):
        self._summarizer = summarizer
        self._style_profiler = style_profiler
        self._jobs: Dict[str, AnalyzeJob] = {}
        self._lock = threading.Lock()

    def start(
        self,
        book_title: str,
        chapters: List[Chapter],
        indices: Optional[List[int]] = None,
        *,
        extract_style: bool = True,
        prior_fine: Optional[List] = None,
    ) -> AnalyzeJob:
        target_indices = sorted(set(indices if indices is not None else [c.index for c in chapters]))
        ch_map = {c.index: c for c in chapters}
        target = [ch_map[i] for i in target_indices if i in ch_map]
        if not target:
            raise ValueError("无有效章节可摘要")

        style_description = ""
        anti_ai_directive = ""
        style_samples: List[str] = []
        if extract_style:
            profile = self._style_profiler.profile(chapters[:3])
            style_description = profile.description
            anti_ai_directive = profile.anti_ai_directive
            style_samples = list(profile.samples)

        job = AnalyzeJob(
            job_id=uuid.uuid4().hex,
            book_title=book_title,
            chapters=chapters,
            indices=target_indices,
            style_description=style_description,
            anti_ai_directive=anti_ai_directive,
            style_samples=style_samples,
            total_count=len(target),
            prior_fine_seed=list(prior_fine or []),
        )
        with self._lock:
            self._jobs[job.job_id] = job
        thread = threading.Thread(target=self._run_job, args=(job.job_id,), daemon=True)
        thread.start()
        return job

    def get_job(self, job_id: str) -> Optional[AnalyzeJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        """请求停止任务：当前波次摘要完成后不再继续后续章节。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status in {"done", "error"}:
                return False
            if job.cancelled or job.status == "cancelled":
                return True
            job.cancelled = True
            return True

    def subscribe(self, job_id: str) -> Queue:
        q: Queue = Queue()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"unknown job {job_id}")
            job.subscribers.append(q)
            for event in job.event_log:
                q.put(event)
        return q

    def iter_events(self, job_id: str, *, poll_timeout: float = 30.0) -> Iterator[str]:
        """SSE 生成器：yield `data: {...}\\n\\n` 行。"""
        event_q = self.subscribe(job_id)
        while True:
            try:
                event = event_q.get(timeout=poll_timeout)
            except Empty:
                # 心跳，避免代理断连
                yield ": keepalive\n\n"
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job and job.status in {"done", "error", "cancelled"}:
                        yield self._format_sse(self._terminal_event(job))
                        return
                continue
            yield self._format_sse(event)
            if event.get("type") in {"analyze_done", "analyze_error", "analyze_cancelled"}:
                return

    def _format_sse(self, event: dict) -> str:
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    def _snapshot_event(self, job: AnalyzeJob) -> dict:
        return {
            "type": "analyze_progress",
            "job_id": job.job_id,
            "status": job.status,
            "done": job.done_count,
            "total": job.total_count,
            "style_description": job.style_description,
            "anti_ai_directive": job.anti_ai_directive,
            "style_samples": job.style_samples,
            "error": job.error,
        }

    def _terminal_event(self, job: AnalyzeJob) -> dict:
        if job.status == "error":
            return {
                "type": "analyze_error",
                "job_id": job.job_id,
                "detail": job.error or "unknown error",
                "done": job.done_count,
                "total": job.total_count,
            }
        if job.status == "cancelled":
            return {
                "type": "analyze_cancelled",
                "job_id": job.job_id,
                "done": job.done_count,
                "total": job.total_count,
                "style_description": job.style_description,
                "anti_ai_directive": job.anti_ai_directive,
                "style_samples": job.style_samples,
            }
        return {
            "type": "analyze_done",
            "job_id": job.job_id,
            "done": job.done_count,
            "total": job.total_count,
            "style_description": job.style_description,
            "anti_ai_directive": job.anti_ai_directive,
            "style_samples": job.style_samples,
        }

    def _emit(self, job: AnalyzeJob, event: dict) -> None:
        job.event_log.append(event)
        for q in list(job.subscribers):
            try:
                q.put(event, block=False)
            except Exception:
                pass

    def _finish_job(self, job: AnalyzeJob) -> None:
        with self._lock:
            if job.cancelled:
                job.status = "cancelled"
            elif job.status != "error":
                job.status = "done"
        self._emit(job, self._terminal_event(job))

    def _emit_chapter_ready(
        self,
        job: AnalyzeJob,
        ch: Chapter,
        summaries: list,
        *,
        duration_s: float,
    ) -> None:
        payload = {
            "type": "chapter_ready",
            "job_id": job.job_id,
            "chapter_index": ch.index,
            "title": ch.title,
            "summaries": [
                {
                    "chapter_index": s.chapter_index,
                    "title": s.title,
                    "tier": s.tier.value,
                    "text": s.text,
                }
                for s in summaries
            ],
            "duration_s": round(duration_s, 2),
        }
        with self._lock:
            job.done_count += 1
        self._emit(job, payload)
        self._emit(job, self._snapshot_event(job))

    def _summarize_wave(
        self,
        job: AnalyzeJob,
        wave_indices: List[int],
        ch_map: Dict[int, Chapter],
        prior_snapshot: list,
    ) -> list[tuple[Chapter, list, float]]:
        if len(wave_indices) == 1:
            idx = wave_indices[0]
            ch = ch_map[idx]
            started = time.time()
            summaries = self._summarizer.summarize_chapter_tiers(ch, prior_snapshot)
            return [(ch, summaries, time.time() - started)]

        results: list[tuple[Chapter, list, float]] = []
        with ThreadPoolExecutor(max_workers=len(wave_indices)) as pool:
            future_map = {}
            for idx in wave_indices:
                ch = ch_map[idx]
                started = time.time()
                future = pool.submit(
                    self._summarizer.summarize_chapter_tiers,
                    ch,
                    prior_snapshot,
                )
                future_map[future] = (ch, started)

            for future in as_completed(future_map):
                ch, started = future_map[future]
                results.append((ch, future.result(), time.time() - started))

        results.sort(key=lambda item: item[0].index)
        return results

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
        self._emit(job, self._snapshot_event(job))

        ch_map = {c.index: c for c in job.chapters}
        prior_fine = list(job.prior_fine_seed)
        workers = SUMMARY_CONCURRENCY
        try:
            for wave_start in range(0, len(job.indices), workers):
                with self._lock:
                    should_stop = job.cancelled
                if should_stop:
                    self._finish_job(job)
                    return

                wave_indices = job.indices[wave_start : wave_start + workers]
                prior_snapshot = list(prior_fine)
                wave_results = self._summarize_wave(job, wave_indices, ch_map, prior_snapshot)

                for ch, summaries, duration_s in wave_results:
                    prior_fine.append(summaries[0])
                    self._emit_chapter_ready(job, ch, summaries, duration_s=duration_s)

                with self._lock:
                    should_stop = job.cancelled
                if should_stop:
                    self._finish_job(job)
                    return

            self._finish_job(job)
        except Exception as exc:
            log.exception("analyze job %s failed", job_id)
            with self._lock:
                job.status = "error"
                job.error = str(exc)
            self._emit(job, self._terminal_event(job))
