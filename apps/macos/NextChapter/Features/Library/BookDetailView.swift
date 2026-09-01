import SwiftUI

struct BookDetailView: View {
    let book: Book
    @EnvironmentObject private var core: CoreClient
    @EnvironmentObject private var bookStore: BookStore
    @State private var isAnalyzing = false
    @State private var isIncrementalSummarizing = false
    @State private var analyzeError: String?
    @State private var incrementalError: String?
    @State private var analyzeProgress: String?
    @State private var analyzeEventTask: Task<Void, Never>?
    @State private var currentAnalyzeJobId: String?
    @State private var analyzeFinish: ((Result<Void, Error>) -> Void)?
    @State private var displayMode: ChapterDisplayMode = .original
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
                if isAnalyzing || isIncrementalSummarizing {
                    HStack(spacing: 8) {
                        ProgressView()
                        Button {
                            stopAnalyze()
                        } label: {
                            Label("停止摘要", systemImage: "stop.fill")
                        }
                        .buttonStyle(.bordered)
                        .tint(.red)
                        .help("停止当前摘要任务，已完成的章节摘要会保留")
                    }
                }

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

            chapterList

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
            if let progress = analyzeProgress {
                Text(progress)
                    .foregroundStyle(.secondary)
                    .font(.callout)
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onAppear { syncDisplayMode() }
        .onChange(of: book.id) { _, _ in syncDisplayMode() }
        .onDisappear { stopAnalyze() }
    }

    private func stopAnalyze() {
        analyzeEventTask?.cancel()
        analyzeEventTask = nil
        if let jobId = currentAnalyzeJobId {
            let id = jobId
            Task { try? await core.cancelAnalyze(jobId: id) }
        }
        currentAnalyzeJobId = nil
        if let finish = analyzeFinish {
            analyzeFinish = nil
            finish(.failure(CancellationError()))
        }
        isAnalyzing = false
        isIncrementalSummarizing = false
        analyzeProgress = nil
    }

    private func syncDisplayMode() {
        displayMode = book.summaries.isEmpty ? .original : .summary
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
                if let sum = book.summaries.first(where: { $0.chapter_index == ch.index && $0.tier == "fine" }) {
                    Text(normalizeSummaryText(sum.text))
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

    /// 修复旧版 render 把 sentences 字符串逐字 join 成多行的问题。
    private func normalizeSummaryText(_ text: String) -> String {
        let lines = text.split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
        guard lines.count >= 4, lines.allSatisfy({ $0.count == 1 }) else { return text }
        return lines.joined()
    }

    private func toggleExpand(_ index: Int) {
        if expandedChapterIndexes.contains(index) {
            expandedChapterIndexes.remove(index)
        } else {
            expandedChapterIndexes.insert(index)
        }
    }

    private func analyze() async {
        await runAnalyzeAsync(indices: nil, replaceExisting: true, isIncremental: false)
    }

    private func continueSummarize() async {
        let toSummarize = pendingChapters
        guard !toSummarize.isEmpty else { return }
        await runAnalyzeAsync(
            indices: toSummarize.map { $0.index },
            replaceExisting: false,
            isIncremental: true
        )
    }

    /// 后台逐章摘要（Lumina 式 SSE），避免长书 HTTP 超时。
    private func runAnalyzeAsync(indices: [Int]?, replaceExisting: Bool, isIncremental: Bool) async {
        if isIncremental {
            isIncrementalSummarizing = true
            incrementalError = nil
        } else {
            isAnalyzing = true
            analyzeError = nil
        }
        analyzeProgress = "正在启动分析…"
        analyzeEventTask?.cancel()

        defer {
            if isIncremental { isIncrementalSummarizing = false }
            else { isAnalyzing = false }
        }

        do {
            let existing = replaceExisting ? [] : book.summaries.filter { $0.tier == "fine" }
            let start = try await core.startAnalyze(
                bookTitle: book.title,
                chapters: book.chapters,
                indices: indices,
                existingSummaries: existing
            )

            var updated = book
            if replaceExisting {
                updated.summaries = []
            }
            updated.styleDescription = start.style_description
            updated.antiAIDirective = start.anti_ai_directive
            updated.styleSamples = start.style_samples
            bookStore.update(updated)
            currentAnalyzeJobId = start.job_id
            analyzeProgress = "摘要中 0/\(start.total) 章…"

            try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
                var finished = false
                analyzeFinish = { result in
                    guard !finished else { return }
                    finished = true
                    analyzeFinish = nil
                    switch result {
                    case .success:
                        cont.resume()
                    case .failure(let err):
                        cont.resume(throwing: err)
                    }
                }
                analyzeEventTask = core.subscribeAnalyzeEvents(jobId: start.job_id) { event in
                    Task { @MainActor in
                        guard let type = event["type"] as? String else { return }
                        switch type {
                        case "chapter_ready":
                            mergeChapterSummaries(from: event, into: &updated)
                            bookStore.update(updated)
                            if let done = event["chapter_index"] as? Int {
                                let count = updated.summarizedChapterCount
                                analyzeProgress = "摘要中 · 已完成第 \(done + 1) 章（共 \(count)/\(book.chapters.count)）"
                            }
                        case "analyze_progress":
                            if let done = event["done"] as? Int, let total = event["total"] as? Int {
                                analyzeProgress = "摘要中 \(done)/\(total) 章…"
                            }
                        case "analyze_done":
                            analyzeProgress = nil
                            analyzeFinish?(.success(()))
                        case "analyze_cancelled":
                            analyzeProgress = nil
                            analyzeFinish?(.success(()))
                        case "analyze_error":
                            analyzeProgress = nil
                            let detail = (event["detail"] as? String) ?? "未知错误"
                            analyzeFinish?(.failure(NSError(
                                domain: "NextChapter", code: 502,
                                userInfo: [NSLocalizedDescriptionKey: detail]
                            )))
                        default:
                            break
                        }
                    }
                }
            }
            currentAnalyzeJobId = nil
        } catch is CancellationError {
            analyzeProgress = nil
        } catch {
            analyzeProgress = nil
            if isIncremental {
                incrementalError = "继续摘要失败：\(error.localizedDescription)"
            } else {
                analyzeError = "分析失败：\(error.localizedDescription)"
            }
        }
    }

    private func mergeChapterSummaries(from event: [String: Any], into book: inout Book) {
        guard let rows = event["summaries"] as? [[String: Any]] else { return }
        var keys = Set(book.summaries.map { "\($0.chapter_index)-\($0.tier)" })
        for row in rows {
            guard let idx = row["chapter_index"] as? Int,
                  let title = row["title"] as? String,
                  let tier = row["tier"] as? String,
                  let text = row["text"] as? String else { continue }
            let key = "\(idx)-\(tier)"
            guard !keys.contains(key) else { continue }
            book.summaries.append(.init(chapter_index: idx, title: title, tier: tier, text: text))
            keys.insert(key)
        }
        book.summaries.sort {
            if $0.chapter_index != $1.chapter_index { return $0.chapter_index < $1.chapter_index }
            return tierOrder($0.tier) < tierOrder($1.tier)
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
