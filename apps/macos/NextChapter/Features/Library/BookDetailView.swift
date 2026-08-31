import SwiftUI

struct BookDetailView: View {
    let book: Book
    @EnvironmentObject private var core: CoreClient
    @EnvironmentObject private var bookStore: BookStore
    @State private var isAnalyzing = false
    @State private var isIncrementalSummarizing = false
    @State private var analyzeError: String?
    @State private var incrementalError: String?
    @State private var displayMode: ChapterDisplayMode = .summary
    @State private var expandedChapterIndexes: Set<Int> = []

    enum ChapterDisplayMode: String, CaseIterable, Identifiable {
        case summary = "摘要"
        case original = "原文"
        var id: String { rawValue }
    }

    /// 还没摘要的章节（按 chapter_index 比对）。
    /// 用于：1) 顶部按钮的 X 计数；2) 章节列表的「未摘要」标记。
    private var pendingChapters: [CoreClient.ChapterDTO] {
        let summarizedIndexes = Set(book.summaries.map { $0.chapter_index })
        return book.chapters.filter { !summarizedIndexes.contains($0.index) }
    }

    @ViewBuilder
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(book.title).font(.largeTitle.bold())
                    Text(book.author.isEmpty ? "佚名" : book.author)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if isAnalyzing { ProgressView() }
                if isIncrementalSummarizing { ProgressView() }

                // 继续摘要：仅当存在未摘要章节时显示
                if !pendingChapters.isEmpty {
                    Button {
                        Task { await continueSummarize() }
                    } label: {
                        Label("继续摘要（\(pendingChapters.count) 章）",
                              systemImage: "text.badge.plus")
                    }
                    .buttonStyle(.bordered)
                    .disabled(isIncrementalSummarizing || isAnalyzing)
                    .help("对新增/还没摘要的章节做增量摘要")
                }

                Button {
                    Task { await analyze() }
                } label: {
                    Label(book.summaries.isEmpty ? "开始分析" : "重新分析", systemImage: "sparkles")
                }
                .buttonStyle(.borderedProminent)
                .disabled(isAnalyzing || isIncrementalSummarizing || book.chapters.isEmpty)

                Button {
                    _ = BookExporter.saveTXTWithPanel(book)
                } label: {
                    Label("导出 TXT", systemImage: "square.and.arrow.up")
                }
                .buttonStyle(.bordered)
                .disabled(book.chapters.isEmpty)
                .help("把全书（含续写章节）导出为 TXT")
            }

            Divider()

            if book.summaries.isEmpty && displayMode == .summary {
                ContentUnavailableView(
                    "尚未分析",
                    systemImage: "sparkles",
                    description: Text("点击「开始分析」对全书做滚动摘要与风格提取。这会调用云端 LLM（DeepSeek/Claude）。")
                )
            } else {
                chapterList
            }

            if let err = analyzeError {
                Text(err)
                    .foregroundStyle(.red)
                    .font(.callout)
            }
            if let err = incrementalError {
                Text(err)
                    .foregroundStyle(.red)
                    .font(.callout)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var chapterList: some View {
        List {
            Section {
                ForEach(book.chapters) { ch in
                    chapterRow(ch)
                }
            } header: {
                HStack {
                    Text("章节（\(book.chapters.count)）")
                    if !pendingChapters.isEmpty {
                        Text("· 待摘要 \(pendingChapters.count) 章")
                            .foregroundStyle(.orange)
                    }
                    Spacer()
                    Picker("", selection: $displayMode) {
                        ForEach(ChapterDisplayMode.allCases) { mode in
                            Text(mode.rawValue).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    .fixedSize()
                    .labelsHidden()
                }
            }
        }
    }

    @ViewBuilder
    private func chapterRow(_ ch: CoreClient.ChapterDTO) -> some View {
        let isExpanded = expandedChapterIndexes.contains(ch.index)
        let isPending = !book.summaries.contains(where: { $0.chapter_index == ch.index })
        VStack(alignment: .leading, spacing: 6) {
            Button {
                toggleExpand(ch.index)
            } label: {
                HStack(alignment: .firstTextBaseline) {
                    Text(ch.title)
                        .font(.headline)
                        .foregroundStyle(.primary)
                    if ch.kind == "续写" {
                        Text("续写")
                            .font(.caption2)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.accentColor.opacity(0.18))
                            .foregroundStyle(.tint)
                            .cornerRadius(4)
                    }
                    if isPending {
                        Text("未摘要")
                            .font(.caption2)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.orange.opacity(0.18))
                            .foregroundStyle(.orange)
                            .cornerRadius(4)
                    }
                    Spacer()
                    Text("\(ch.char_count) 字")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            switch displayMode {
            case .summary:
                if let sum = book.summaries.first(where: { $0.chapter_index == ch.index }) {
                    Text(sum.text)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(isExpanded ? nil : 4)
                        .textSelection(.enabled)
                } else if isPending {
                    Text("未摘要 · 待处理（点上方「继续摘要」生成）")
                        .font(.caption)
                        .foregroundStyle(.orange)
                } else {
                    Text("未生成摘要")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            case .original:
                if ch.body.isEmpty {
                    Text("（原文为空）")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                } else {
                    Text(ch.body)
                        .font(.callout)
                        .foregroundStyle(.primary)
                        .lineLimit(isExpanded ? nil : 12)
                        .textSelection(.enabled)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func toggleExpand(_ index: Int) {
        if expandedChapterIndexes.contains(index) {
            expandedChapterIndexes.remove(index)
        } else {
            expandedChapterIndexes.insert(index)
        }
    }

    private func analyze() async {
        isAnalyzing = true
        defer { isAnalyzing = false }
        analyzeError = nil
        do {
            // 一步：风格 + 三档摘要（coarse/ultra 从 fine 派生，省 token）
            let resp = try await core.analyze(bookTitle: book.title, chapters: book.chapters)
            var updated = book
            updated.styleDescription = resp.style_description
            updated.antiAIDirective = resp.anti_ai_directive
            updated.styleSamples = resp.style_samples
            updated.summaries = resp.summaries
            bookStore.update(updated)
        } catch {
            analyzeError = "分析失败：\(error.localizedDescription)"
        }
    }

    /// 增量摘要：只对还没摘要的章节调 /analyze，风格不变，结果合并回 book.summaries。
    /// 老章节摘要不动。
    private func continueSummarize() async {
        let toSummarize = pendingChapters
        guard !toSummarize.isEmpty else { return }
        isIncrementalSummarizing = true
        defer { isIncrementalSummarizing = false }
        incrementalError = nil
        do {
            let resp = try await core.analyze(
                bookTitle: book.title,
                chapters: book.chapters,
                indices: toSummarize.map { $0.index }
            )
            // 用 chapter_index + tier 合并：避免重复（pending 章节理论上没摘要，但保险）
            var existingKeys = Set(book.summaries.map { "\($0.chapter_index)-\($0.tier)" })
            var merged = book.summaries
            for s in resp.summaries where !existingKeys.contains("\(s.chapter_index)-\(s.tier)") {
                merged.append(s)
                existingKeys.insert("\(s.chapter_index)-\(s.tier)")
            }
            // 按 chapter_index + tier 排序，保持稳定顺序
            merged.sort {
                if $0.chapter_index != $1.chapter_index { return $0.chapter_index < $1.chapter_index }
                return tierOrder($0.tier) < tierOrder($1.tier)
            }
            var updated = book
            updated.summaries = merged
            bookStore.update(updated)
        } catch {
            incrementalError = "继续摘要失败：\(error.localizedDescription)"
        }
    }

    private func tierOrder(_ tier: String) -> Int {
        switch tier {
        case "fine": return 0
        case "coarse": return 1
        case "ultra": return 2
        default: return 99
        }
    }
}
