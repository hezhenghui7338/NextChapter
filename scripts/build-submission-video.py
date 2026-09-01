#!/usr/bin/env python3
"""按 docs/SUBMISSION.md 生成 ≤5 分钟汇报录屏（1080p + 中文旁白）。

用法:
  python3 scripts/build-submission-video.py
  python3 scripts/build-submission-video.py --skip-screenshots   # 仅重合成
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WORKDIR = ROOT / "docs" / "video-work"
OUTPUT = ROOT / "docs" / "NextChapter-submission.mp4"
FONT = "/System/Library/Fonts/PingFang.ttc"
VOICE = "Ting-Ting"
BOOK_ID = "5E522B0C-94FB-4BDC-8DEF-59DA6C2B9534"  # 斗罗大陆-前60章（已分析）


@dataclass
class Segment:
    name: str
    kind: str  # slide | screenshot
    duration_hint: float
    narration: str
    slide_lines: list[str] | None = None
    screenshot: str | None = None


SEGMENTS: list[Segment] = [
    Segment(
        name="01-problem",
        kind="slide",
        duration_hint=45,
        narration=(
            "中文网文作者连载时常遇到三类 AI 续写失败：风格跑偏、AI 味重；情节脱节，忘记前文设定；"
            "结构失控，字数、节奏、爽点不对。通用 Chat 式写作工具不理解网文工作流。"
            "作者已有几十到上千章成稿，需要的是接续既有文风与剧情，而不是从零胡写。"
            "NextChapter 的定位是中文网文专用的下一章协作工作台："
            "导入整本书，让 AI 吃透前文，三选一动线出下一章，再做一致性校验。"
        ),
        slide_lines=[
            "NextChapter",
            "中文网文 AI 续写助手",
            "",
            "解决三类续写失败：",
            "· 风格跑偏（AI 味重）",
            "· 情节脱节（遗忘设定）",
            "· 结构失控（节奏/爽点）",
        ],
    ),
    Segment(
        name="02-demo-settings",
        kind="screenshot",
        duration_hint=12,
        narration="首先进入设置页，配置云端 LLM。API Key 仅存本机 UserDefaults，不会上传。",
        screenshot="settings.png",
    ),
    Segment(
        name="03-demo-library",
        kind="screenshot",
        duration_hint=18,
        narration=(
            "书库 Tab 导入 TXT 网文，系统自动识别书名并按「第 X 章」切分。"
            "选中作品后点击「开始分析」，完成风格抽取与逐章摘要。"
        ),
        screenshot="library.png",
    ),
    Segment(
        name="04-demo-summaries",
        kind="screenshot",
        duration_hint=22,
        narration=(
            "分析完成后，章节列表可切换「摘要 / 原文」视图。"
            "长书采用三档滚动摘要加 25 章滑动窗口：近章保细节，远章压缩，在 token 预算内最大化连贯性。"
        ),
        screenshot="library-summary.png",
    ),
    Segment(
        name="05-demo-continue",
        kind="screenshot",
        duration_hint=28,
        narration=(
            "切到续章 Tab，填写下一章标题与目标字数。"
            "A 动线「一键续写」适合日常更新：点一下，AI 基于上下文与风格向量直接出章。"
        ),
        screenshot="continue.png",
    ),
    Segment(
        name="06-demo-consistency",
        kind="screenshot",
        duration_hint=18,
        narration=(
            "生成后可做一致性检查，扫描人物状态、世界规则与剧情伏笔是否与前文冲突。"
            "也可 AI 重写，满意后采纳加入原文或复制导出。"
        ),
        screenshot="continue-result.png",
    ),
    Segment(
        name="07-demo-plan",
        kind="screenshot",
        duration_hint=12,
        narration=(
            "C 动线「AI 规划续写」适合卡文场景：AI 先出五维规划初稿，"
            "讨论编辑后锁定，再按规划生成正文。三条动线互斥，避免串台。"
        ),
        screenshot="continue-plan.png",
    ),
    Segment(
        name="08-tech-choices",
        kind="slide",
        duration_hint=60,
        narration=(
            "关键技术选择：Swift macOS 加 Python sidecar，沿用 Lumina 架构，"
            "SwiftUI 做原生体验，Python 承载 NLP 与 LLM 管线，sidecar 随 App 打包，用户零配置。"
            "云端 LLM 优先，中文网文续写质量显著优于本地小模型，API Key 用户自备。"
            "25 章滑动窗口加三档摘要，在 token 预算内最大化连贯性。"
            "A、B、C 三选一动线对应日常更新、有腹稿控剧情、卡文碰撞思路，互斥避免串台。"
            "MVP 先做轻量一致性检查，完整 fact-bank 留 Phase 3。"
        ),
        slide_lines=[
            "关键技术与产品选择",
            "",
            "Swift macOS + Python sidecar",
            "云端 LLM（DeepSeek 等）",
            "25 章窗口 + 三档摘要",
            "A/B/C 三动线互斥",
            "轻量一致性 → fact-bank",
        ],
    ),
    Segment(
        name="09-ai-dev",
        kind="slide",
        duration_hint=45,
        narration=(
            "本项目是 AI 原生开发的典型实践，Cursor Agent 贯穿全流程。"
            "产品设计：从 PRD 草稿讨论出完整 PRD，含三动线互斥、API 契约与验收标准。"
            "架构与实现：AI 生成 Python sidecar 与 SwiftUI 三 Tab 界面，人负责方向拍板与联调验收。"
            "测试与发版：93 项单元与 E2E 测试，build-release 一键打包 DMG。"
            "人的角色是定产品边界、评审 PRD、验证续写质量；AI 负责样板代码、测试与文档。"
        ),
        slide_lines=[
            "AI 如何参与开发",
            "",
            "Cursor Agent 全流程",
            "· PRD 结构化",
            "· sidecar + SwiftUI 实现",
            "· 93 项测试 + 发版脚本",
            "人：边界 · 质量验收",
        ],
    ),
    Segment(
        name="10-boundary",
        kind="slide",
        duration_hint=30,
        narration=(
            "v0.1.1 已完成：导入、切分、三档摘要、风格向量、三动线续写、"
            "轻量一致性与 AI 重写，macOS 公开发版与 93 项测试。"
            "未完成：fact-bank 完整一致性、Windows、EPUB 导入、分析缓存秒开。"
            "实际投入约 1 个工作日，AI 辅助将 PRD 预估的三到五周 MVP 压缩到单日可交付。"
        ),
        slide_lines=[
            "完成边界 · v0.1.1",
            "",
            "✅ 导入 / 分析 / 三动线续写",
            "✅ 一致性 / AI 重写 / macOS 发版",
            "",
            "⬜ fact-bank · Windows · EPUB",
            "投入：约 1 工作日",
        ],
    ),
]

SCREENSHOT_SPECS = {
    "settings.png": ("settings", None),
    "library.png": ("library", BOOK_ID),
    "library-summary.png": ("library", BOOK_ID),
    "continue.png": ("continue", BOOK_ID),
    "continue-result.png": ("continue", BOOK_ID),
    "continue-plan.png": ("continue", BOOK_ID),
}


def run(cmd: list[str], **kwargs) -> None:
    print("→", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def say_to_aac(text: str, out_aac: Path) -> float:
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp_aiff:
        aiff = Path(tmp_aiff.name)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp_txt:
        tmp_txt.write(text)
        txt_path = Path(tmp_txt.name)
    try:
        run(["say", "-v", VOICE, "-r", "165", "-f", str(txt_path), "-o", str(aiff)])
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(aiff),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(out_aac),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        probe = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(out_aac),
            ],
            text=True,
        )
        return float(probe.strip())
    finally:
        aiff.unlink(missing_ok=True)
        txt_path.unlink(missing_ok=True)


def escape_drawtext(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_slide_png(lines: list[str], out: Path) -> None:
    img = Image.new("RGB", (1920, 1080), color=(26, 26, 46))
    draw = ImageDraw.Draw(img)
    y = 140
    for i, line in enumerate(lines):
        if not line:
            y += 24
            continue
        size = 54 if i == 0 else (42 if i == 1 else 34)
        color = (255, 255, 255) if i < 2 else (224, 224, 224)
        font = load_font(size)
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((1920 - tw) // 2, y), line, font=font, fill=color)
        y += int(size * 1.35) + 8
    logo = ROOT / "docs" / "assets" / "logo.png"
    if logo.exists():
        mark = Image.open(logo).convert("RGBA")
        mark.thumbnail((320, 180))
        img.paste(mark, ((1920 - mark.width) // 2, min(y + 20, 820)), mark)
    img.save(out)


def make_slide_video(lines: list[str], audio: Path, duration: float, out: Path) -> None:
    slide_png = out.with_suffix(".png")
    render_slide_png(lines, slide_png)
    make_screenshot_video(slide_png, audio, duration, out)


def crop_app_window(raw: Path, out: Path) -> None:
    """从全屏截图中裁出居中的 App 窗口区域。"""
    probe = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(raw),
        ],
        text=True,
    ).strip()
    sw, sh = map(int, probe.split(","))
    # App 默认 1200×800，居中；留少量边距
    w, h = min(1280, sw - 80), min(860, sh - 120)
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2 - 20)
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw),
            "-vf",
            f"crop={w}:{h}:{x}:{y},scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#1a1a2e",
            "-frames:v",
            "1",
            str(out),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def make_screenshot_video(image: Path, audio: Path, duration: float, out: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-i",
            str(audio),
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#1a1a2e",
            "-c:v",
            "libx264",
            "-tune",
            "stillimage",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            f"{duration:.3f}",
            str(out),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def find_app_binary() -> Path:
    macos = ROOT / "apps" / "macos"
    for candidate in (
        macos / ".build" / "release" / "NextChapter",
        macos / ".build" / "arm64-apple-macosx" / "release" / "NextChapter",
    ):
        if candidate.exists():
            return candidate
    dist = ROOT / "dist" / "NextChapter.app" / "Contents" / "MacOS" / "NextChapter"
    if dist.exists():
        return dist
    raise FileNotFoundError("找不到 NextChapter 可执行文件，请先运行 swift build -c release")


def wait_for_sidecar(timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    url = "http://127.0.0.1:18432/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise TimeoutError("sidecar 未在时限内启动")


def sync_app_bundle(app_bin: Path) -> Path:
    """将最新编译产物同步到 .app，便于 open --env 传参。"""
    app = ROOT / "dist" / "NextChapter.app"
    target = app / "Contents" / "MacOS" / "NextChapter"
    if app.exists() and app_bin.exists():
        shutil.copy2(app_bin, target)
        return app
    return app_bin


def launch_app(app_path: Path, env: dict[str, str]) -> subprocess.Popen | None:
    merged = os.environ.copy()
    merged.update(env)
    if str(app_path).endswith(".app"):
        cmd = ["open", "-n", "-a", str(app_path)]
        for k, v in env.items():
            cmd.extend(["--env", f"{k}={v}"])
        subprocess.run(cmd, check=True)
        return None
    return subprocess.Popen([str(app_path)], env=merged, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def capture_frame(raw: Path, out: Path) -> None:
    for _ in range(3):
        subprocess.run(["osascript", "-e", 'tell application "NextChapter" to activate'], check=False)
        time.sleep(1.2)
    run(["screencapture", "-x", str(raw)])
    crop_app_window(raw, out)


def capture_screenshots(app_bin: Path) -> None:
    screens = WORKDIR / "screens"
    raw_dir = WORKDIR / "raw"
    screens.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    app_path = sync_app_bundle(app_bin)
    subprocess.run(["pkill", "-x", "NextChapter"], stderr=subprocess.DEVNULL)
    time.sleep(1)

    for fname, (tab, book_id) in SCREENSHOT_SPECS.items():
        print(f"\n📸 截取 {fname} (tab={tab})")
        subprocess.run(["pkill", "-x", "NextChapter"], stderr=subprocess.DEVNULL)
        time.sleep(0.5)

        env: dict[str, str] = {"NC_DEMO_TAB": tab}
        if book_id:
            env["NC_DEMO_BOOK"] = book_id

        launch_app(app_path, env)
        wait_for_sidecar()
        extra = 5.0 if tab == "continue" else 3.0
        time.sleep(extra)

        raw_path = raw_dir / fname.replace(".png", "-raw.png")
        capture_frame(raw_path, screens / fname)

        subprocess.run(["pkill", "-x", "NextChapter"], stderr=subprocess.DEVNULL)
        time.sleep(1)


def build_video(skip_screenshots: bool) -> Path:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    audio_dir = WORKDIR / "audio"
    parts_dir = WORKDIR / "parts"
    for d in (audio_dir, parts_dir):
        d.mkdir(parents=True, exist_ok=True)

    if not skip_screenshots:
        print("\n🔨 编译 macOS App（release）…")
        macos = ROOT / "apps" / "macos"
        run(["swift", "build", "-c", "release"], cwd=str(macos))
        app_bin = find_app_binary()
        capture_screenshots(app_bin)

    part_files: list[Path] = []
    total = 0.0
    max_total = 300.0

    for seg in SEGMENTS:
        print(f"\n🎙  段落 {seg.name}")
        aac = audio_dir / f"{seg.name}.aac"
        dur = say_to_aac(seg.narration, aac)
        seg_dur = dur + 0.6
        if total + seg_dur > max_total:
            seg_dur = max(3.0, max_total - total)
        total += seg_dur

        part = parts_dir / f"{seg.name}.mp4"
        if seg.kind == "slide":
            assert seg.slide_lines
            make_slide_video(seg.slide_lines, aac, seg_dur, part)
        else:
            img = WORKDIR / "screens" / seg.screenshot
            if not img.exists():
                raise FileNotFoundError(f"缺少截图 {img}，请先去掉 --skip-screenshots")
            make_screenshot_video(img, aac, seg_dur, part)
        part_files.append(part)
        print(f"   时长 {seg_dur:.1f}s（累计 {total:.1f}s）")

    concat_list = WORKDIR / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p}'" for p in part_files) + "\n", encoding="utf-8")
    tmp_out = WORKDIR / "submission-raw.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(tmp_out),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 确保总时长 ≤ 5 分钟
    raw_dur = float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(tmp_out),
            ],
            text=True,
        ).strip()
    )
    if raw_dur > max_total:
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(tmp_out),
                "-t",
                str(max_total),
                "-c",
                "copy",
                str(OUTPUT),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        shutil.copy2(tmp_out, OUTPUT)

    final_dur = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(OUTPUT),
        ],
        text=True,
    )
    print(f"\n✅ 视频已生成: {OUTPUT}")
    print(f"   总时长: {float(final_dur.strip()):.1f}s")
    return OUTPUT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-screenshots", action="store_true")
    args = parser.parse_args()
    if shutil.which("ffmpeg") is None or shutil.which("say") is None:
        sys.exit("需要 ffmpeg 与 say 命令")
    build_video(skip_screenshots=args.skip_screenshots)


if __name__ == "__main__":
    main()
