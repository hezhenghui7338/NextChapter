import AppKit
import SwiftUI

/// 续章主流程：三种动线（A 一键 / B 用户规划 / C AI 规划）三选一。
///
/// 顶层布局：
/// 1. 顶部表单：章节号 / 目标字数（三种动线共用）
/// 2. 动线选择 radio：互斥，切换时清空中间态（F10d）
/// 3. 动线专属输入区：
///    - A：直接「一键续写」
///    - B：5 维规划输入框 + 「按我的规划续写」
///    - C：分三段：①一键让 AI 出规划初稿；②编辑初稿 + 可选「和 AI 讨论」；③「锁定规划」+「按规划续写」
/// 4. 结果区（生成后显示，含 4 个动作 + 一致性 + AI 重写）
///
/// 切换动线时清空所有动线专属状态，避免 A/B/C 之间的中间态串台。
struct ContinueView: View {
    @EnvironmentObject private var core: CoreClient
    @EnvironmentObject private var bookStore: BookStore
    @EnvironmentObject private var nav: AppNav
    @EnvironmentObject private var settings: AppSettings
    @Binding var selectedBookId: String?

    // MARK: - 动线状态
    @State private var mode: CoreClient.ContinueMode = .auto

    // MARK: - A 动线状态（无）

    // MARK: - B 动线状态
    @State private var userPlan: String = ""  // 用户填的规划（B 动线）

    // MARK: - C 动线状态
    /// C 动线分三段：
    /// 1. **出初稿**：点"让 AI 出规划" → AI 起一份 5 维初稿
    /// 2. **编辑 / 讨论**：用户改初稿，可展开讨论面板让 AI 改写
    /// 3. **锁定**：用户把当前文本存为 finalPlan，点"按规划续写"
    @State private var initialPlan: String = ""              // AI 出的初稿（用户可继续编辑）
    @State private var hasInitialPlan: Bool = false          // 是否已生成过初稿
    @State private var showDiscussion: Bool = false          // 讨论面板是否展开
    @State private var isPlanning: Bool = false              // AI 正在出 / 改规划
    @State private var turns: [CoreClient.TurnDTO] = []      // plan_turn / plan_revise 多轮历史
    @State private var userInput: String = ""                // 讨论面板里的输入
    @State private var discussionMode: PlanDiscussionMode = .revise  // 讨论 vs 优化
    @State private var finalPlan: String = ""                // 锁定后的纲要（用作 final_plan）
    @State private var planLocked: Bool = false              // 是否已锁定

    // MARK: - 共有
    @State private var generatedBody: String = ""
    @State private var generatedTitle: String = ""
    @State private var consistencyIssues: [CoreClient.ConsistencyIssueDTO] = []
    @State private var consistencySummary: String = ""
    @State private var critiqueSummary: String = ""
    @State private var critiqueIssues: [CoreClient.CritiqueIssueDTO] = []
    @State private var critiqueRevisedBody: String = ""
    @State private var critiqueRevisedTitle: String = ""
    @State private var adopted: Bool = false
    @State private var toast: String? = nil
    @State private var isBusy = false
    @State private var nextChapterHint: String = ""
    @State private var targetChars: Int = 2000
    @State private var lastContextStats: String = ""
    @State private var showBodyPreview: Bool = false  // 正文编辑/预览切换

    var body: some View {
        NavigationSplitView {
            bookPicker
        } detail: {
            if bookStore.books.isEmpty || selectedBookId == nil {
                ContentUnavailableView("请先在书库选择作品", systemImage: "pencil.and.outline")
            } else if let book = currentBook, book.summaries.isEmpty {
                ContentUnavailableView("尚未分析", systemImage: "sparkles",
                                       description: Text("先在「书库」对这本作品做分析，才能续章。"))
            } else if let book = currentBook {
                main(book: book)
            }
        }
    }

    private var bookPicker: some View {
        List(selection: $selectedBookId) {
            ForEach(bookStore.books) { book in
                VStack(alignment: .leading) {
                    Text(book.title).font(.headline)
                    Text(book.summaries.isEmpty ? "未分析" : "已分析 · \(book.summarizedChapterCount) 章")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .tag(book.id)
            }
        }
        .frame(minWidth: 220)
    }

    private var currentBook: Book? {
        guard let id = selectedBookId else { return nil }
        return bookStore.books.first(where: { $0.id == id })
    }

    private func main(book: Book) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                unsummarizedBanner(book: book)
                formBar(book: book)
                modeBar
                styleContextBar(book: book)
                if !generatedBody.isEmpty {
                    resultPanel(book: book)
                } else {
                    hintView
                }
                modePanel(book: book)
            }
            .padding(16)
            .frame(minWidth: 760)
        }
    }

    // MARK: - 顶部表单（章节号 + 目标字数）

    private func formBar(book: Book) -> some View {
        HStack(spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: "number")
                    .foregroundStyle(.secondary)
                TextField("第 X 章", text: $nextChapterHint)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 140)
            }
            HStack(spacing: 6) {
                Image(systemName: "text.alignleft")
                    .foregroundStyle(.secondary)
                Stepper("目标 \(targetChars) 字", value: $targetChars, in: 500...5000, step: 500)
                    .frame(width: 200)
            }
            Spacer()
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }

    // MARK: - 动线选择（互斥 radio）

    private var modeBar: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "arrow.triangle.branch")
                    .foregroundStyle(.secondary)
                Text("续写动线（互斥三选一）")
                    .font(.callout.bold())
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                ForEach(CoreClient.ContinueMode.allCases) { m in
                    modeCard(m)
                }
            }
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }

    private func modeCard(_ m: CoreClient.ContinueMode) -> some View {
        let selected = (m == mode)
        return Button {
            selectMode(m)
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Image(systemName: m.systemImage)
                        .foregroundStyle(selected ? Color.white : Color.accentColor)
                    Text(m.title)
                        .font(.callout.bold())
                        .foregroundStyle(selected ? Color.white : Color.primary)
                }
                Text(m.subtitle)
                    .font(.caption)
                    .foregroundStyle(selected ? Color.white.opacity(0.85) : Color.secondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? Color.accentColor : Color.gray.opacity(0.08))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(selected ? Color.accentColor : Color.gray.opacity(0.25), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    /// 切换动线：清空所有中间态（F10d）。
    /// 已生成的结果（generatedBody 等）保留——用户切换动线后可以基于新动线重生成。
    private func selectMode(_ new: CoreClient.ContinueMode) {
        guard new != mode else { return }
        mode = new
        // A 动线
        // B 动线
        userPlan = ""
        // C 动线
        initialPlan = ""
        hasInitialPlan = false
        showDiscussion = false
        isPlanning = false
        turns = []
        userInput = ""
        discussionMode = .revise
        finalPlan = ""
        planLocked = false
        showToast("已切换到「\(new.title)」")
    }

    // MARK: - 风格 + 上下文状态条

    @ViewBuilder
    private func styleContextBar(book: Book) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "sparkles.rectangle.stack")
                .foregroundStyle(.tint)
            if !book.styleDescription.isEmpty {
                Text(book.styleDescription)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .truncationMode(.tail)
            } else {
                Text("（未抽取风格，请先在「书库」分析）")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            Spacer()
            HStack(spacing: 10) {
                Label(antiAILabel(), systemImage: "shield.lefthalf.filled")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .help("反 AI 味强度（在「设置」修改后需重启 sidecar）")
                if !lastContextStats.isEmpty {
                    Text("上下文：\(lastContextStats)")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                        .help("本次拼装的滑动窗口（细/粗/极简三档）")
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.4))
        .cornerRadius(8)
    }

    private func antiAILabel() -> String {
        switch settings.antiAIPreset {
        case "strong": return "反 AI · 强"
        case "mild": return "反 AI · 弱"
        default: return "反 AI · 默认"
        }
    }

    // MARK: - 未摘要提醒

    @ViewBuilder
    private func unsummarizedBanner(book: Book) -> some View {
        let summarizedIndexes = Set(book.summaries.map { $0.chapter_index })
        let pending = book.chapters.filter { !summarizedIndexes.contains($0.index) }
        if !pending.isEmpty {
            Button {
                nav.go(.library, selectBookId: book.id)
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.bubble.fill")
                        .foregroundStyle(.orange)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("有 \(pending.count) 章还未摘要")
                            .font(.callout.bold())
                            .foregroundStyle(.primary)
                        Text("点此回到「书库」点「继续摘要」，新章节才会进入续写上下文。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.orange.opacity(0.10))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.orange.opacity(0.35), lineWidth: 1)
                )
                .cornerRadius(8)
            }
            .buttonStyle(.plain)
            .help("跳到书库并选中当前作品")
        }
    }

    // MARK: - 提示（按动线显示不同）

    private var hintView: some View {
        VStack(alignment: .leading, spacing: 6) {
            switch mode {
            case .auto:
                Label("点下面的「一键续写」即可", systemImage: "wand.and.stars")
                    .font(.headline)
                Text("AI 会基于最近剧情上下文和原作风格，自动起势续写——不规划、即兴发挥。")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            case .userPlan:
                Label("在下方填好规划，然后点「按我的规划续写」", systemImage: "list.bullet.rectangle")
                    .font(.headline)
                Text("把你想要的剧情走向 / 关键场景 / 爽点 / 节奏 / 坑点写下来，AI 会严格按你的规划写。")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            case .aiPlan:
                Label("先让 AI 一键出规划，满意后锁定再写", systemImage: "bubble.left.and.bubble.right")
                    .font(.headline)
                Text("点「AI 一键生成规划」出初稿；可直接采用、手动编辑，或在讨论区对话要求 AI 优化。")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.5))
        .cornerRadius(10)
    }

    // MARK: - 动线专属输入区

    @ViewBuilder
    private func modePanel(book: Book) -> some View {
        switch mode {
        case .auto:
            autoPanel(book: book)
        case .userPlan:
            userPlanPanel(book: book)
        case .aiPlan:
            aiPlanPanel(book: book)
        }
    }

    /// A 动线：就一个大按钮。
    private func autoPanel(book: Book) -> some View {
        HStack(spacing: 10) {
            Button {
                Task { await generate(book: book) }
            } label: {
                Label("一键续写", systemImage: "wand.and.stars")
                    .font(.title3.bold())
                    .frame(minWidth: 160)
                    .padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)
            .disabled(isBusy)
            .keyboardShortcut(.return, modifiers: [.command])
            Spacer()
            if isBusy { ProgressView() }
            if let toast = toast {
                Text(toast).font(.callout).foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
        .cornerRadius(10)
    }

    /// B 动线：规划输入框 + 「按我的规划续写」按钮。
    private func userPlanPanel(book: Book) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "list.bullet.rectangle")
                    .foregroundStyle(.tint)
                Text("下一章规划（B 动线）")
                    .font(.callout.bold())
                Spacer()
                Text("\(userPlan.count) 字")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text("建议从这 5 个维度描述（也可自由发挥）：")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("· 剧情走向   · 关键场景   · 爽点设计   · 节奏安排   · 坑点 / 填坑")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            TextEditor(text: $userPlan)
                .font(.body)
                .frame(minHeight: 140, maxHeight: 240)
                .border(.separator, width: 1)
                .overlay(alignment: .topLeading) {
                    if userPlan.isEmpty {
                        Text("例如：\n剧情走向：主角与师妹在藏经阁对峙。\n关键场景：发现禁书《天魔策》。\n爽点：师妹震惊之下认出主角真实身份。\n节奏：先用对话铺垫，再用禁书揭底。\n坑点：补上第 80 章『师妹偷看禁书』的伏笔。")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                            .padding(8)
                            .allowsHitTesting(false)
                    }
                }
            HStack(spacing: 10) {
                Button {
                    Task { await generate(book: book) }
                } label: {
                    Label("按我的规划续写", systemImage: "wand.and.stars")
                        .font(.title3.bold())
                        .frame(minWidth: 200)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isBusy || userPlan.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .help("规划为空时不可用")
                .keyboardShortcut(.return, modifiers: [.command])

                Spacer()
                if isBusy { ProgressView() }
                if let toast = toast {
                    Text(toast).font(.callout).foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
        .cornerRadius(10)
    }

    /// C 动线：三段式 UI（出初稿 → 编辑/讨论 → 锁定续写）
    ///
    /// 阶段 1：未出初稿 → 大按钮"让 AI 出一份规划初稿"
    /// 阶段 2：已出初稿未锁定 → 可编辑文本框 + "重新生成" / "和 AI 讨论" / "锁定规划"
    /// 阶段 3：已锁定 → 显示锁定内容 + "解锁" + "按规划续写"
    private func aiPlanPanel(book: Book) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            // 顶部状态条
            aiPlanHeader

            if !hasInitialPlan {
                // 阶段 1：出初稿
                aiPlanInitialStage(book: book)
            } else if planLocked {
                // 阶段 3：已锁定
                aiPlanLockedStage(book: book)
            } else {
                // 阶段 2：编辑 / 讨论
                aiPlanEditingStage(book: book)
            }

            // 讨论面板（按需展开）
            if showDiscussion {
                aiPlanDiscussionPanel(book: book)
            }
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
        .cornerRadius(10)
    }

    private var aiPlanHeader: some View {
        HStack(spacing: 6) {
            Image(systemName: "bubble.left.and.bubble.right")
                .foregroundStyle(.tint)
            Text("规划讨论（C 动线）")
                .font(.callout.bold())
            if planLocked {
                HStack(spacing: 4) {
                    Image(systemName: "lock.fill")
                        .foregroundStyle(.green)
                    Text("已锁定")
                        .font(.caption.bold())
                        .foregroundStyle(.green)
                }
            } else if hasInitialPlan {
                Text("· 初稿可编辑")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if isPlanning { ProgressView().controlSize(.small) }
        }
    }

    /// 阶段 1：未出初稿。一个大按钮 + 简短说明。
    private func aiPlanInitialStage(book: Book) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("AI 会基于最近剧情上下文，从「剧情走向 / 关键场景 / 爽点 / 节奏 / 坑点」五个维度起草一份极简规划（200 字以内）。你可以直接采用、继续编辑，或通过对话要求 AI 优化。")
                .font(.callout)
                .foregroundStyle(.secondary)
            HStack {
                Button {
                    Task { await generateInitialPlan(book: book) }
                } label: {
                    Label("AI 一键生成规划", systemImage: "sparkles")
                        .font(.title3.bold())
                        .frame(minWidth: 220)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isPlanning)
                .keyboardShortcut(.return, modifiers: [.command])
                Spacer()
                if let toast = toast {
                    Text(toast).font(.callout).foregroundStyle(.secondary)
                }
            }
        }
    }

    /// 阶段 2：已出初稿，未锁定。
    private func aiPlanEditingStage(book: Book) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            // 规划编辑器（可改 AI 的初稿）
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("规划初稿（可编辑）")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("\(initialPlan.count) 字")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                TextEditor(text: $initialPlan)
                    .font(.body)
                    .frame(minHeight: 160, maxHeight: 280)
                    .border(.separator, width: 1)
            }

            HStack(spacing: 8) {
                Button {
                    Task { await regenerateInitialPlan(book: book) }
                } label: {
                    Label("重新生成", systemImage: "arrow.clockwise")
                }
                .disabled(isPlanning)
                .help("清空当前初稿和讨论，让 AI 重新起草")

                Button {
                    withAnimation { showDiscussion.toggle() }
                } label: {
                    Label(showDiscussion ? "收起讨论" : "和 AI 讨论优化", systemImage: "bubble.left.and.bubble.right")
                }
                .disabled(isPlanning)
                .help("展开对话面板，讨论建议或直接让 AI 改写规划")

                Spacer()

                Button {
                    adoptCurrentPlan()
                } label: {
                    Label("采用此规划", systemImage: "checkmark.circle")
                        .font(.callout.bold())
                }
                .buttonStyle(.borderedProminent)
                .disabled(initialPlan.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .help("直接使用当前规划并锁定，之后可点「按规划续写」")

                Button {
                    lockCurrentPlan()
                } label: {
                    Label("锁定规划", systemImage: "lock.fill")
                        .font(.callout.bold())
                }
                .buttonStyle(.bordered)
                .disabled(initialPlan.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .help("把当前文本作为最终规划，锁后才能点「按规划续写」")
            }
        }
    }

    /// 阶段 3：已锁定。显示锁定内容，主按钮变成"按规划续写"。
    private func aiPlanLockedStage(book: Book) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Image(systemName: "lock.fill")
                        .foregroundStyle(.green)
                    Text("锁定的规划（用作 final_plan）")
                        .font(.caption.bold())
                        .foregroundStyle(.green)
                    Spacer()
                    Text("\(finalPlan.count) 字")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                    Button("解锁") {
                        planLocked = false
                        // 解锁后让用户继续编辑（initialPlan 同步回 finalPlan）
                        initialPlan = finalPlan
                        showToast("已解锁，可继续编辑 / 讨论")
                    }
                    .buttonStyle(.borderless)
                    .font(.caption)
                }
                ScrollView {
                    Text(finalPlan)
                        .font(.callout)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                        .padding(8)
                }
                .frame(maxHeight: 240)
                .background(Color.green.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.green.opacity(0.3), lineWidth: 1)
                )
                .cornerRadius(6)
            }

            HStack(spacing: 10) {
                Button {
                    Task { await generate(book: book) }
                } label: {
                    Label("按规划续写", systemImage: "wand.and.stars")
                        .font(.title3.bold())
                        .frame(minWidth: 200)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isBusy)
                .keyboardShortcut(.return, modifiers: [.command])
                Spacer()
                if let toast = toast {
                    Text(toast).font(.callout).foregroundStyle(.secondary)
                }
            }
        }
    }

    /// 讨论面板（阶段 2 可展开）：讨论建议 或 AI 直接改写规划。
    private func aiPlanDiscussionPanel(book: Book) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            HStack(spacing: 6) {
                Image(systemName: "bubble.left.and.bubble.right")
                    .foregroundStyle(.tint)
                Text("和 AI 讨论优化")
                    .font(.callout.bold())
                if !turns.isEmpty {
                    Text("· 已 \(turns.count) 轮")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Picker("模式", selection: $discussionMode) {
                    ForEach(PlanDiscussionMode.allCases) { m in
                        Text(m.title).tag(m)
                    }
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 280)
            }

            Text(discussionMode.hint)
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 4)

            if !turns.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(Array(turns.enumerated()), id: \.offset) { _, t in
                            ChatBubble(role: t.role, content: t.content, assistantLabel: discussionMode.assistantLabel)
                        }
                    }
                    .padding(8)
                }
                .frame(minHeight: 120, maxHeight: 220)
                .background(Color.gray.opacity(0.05))
                .cornerRadius(6)
            }

            HStack(alignment: .bottom, spacing: 8) {
                TextEditor(text: $userInput)
                    .frame(minHeight: 50, maxHeight: 90)
                    .border(.separator, width: 1)
                    .overlay(alignment: .topLeading) {
                        if userInput.isEmpty {
                            Text(discussionMode.placeholder)
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                                .padding(6)
                                .allowsHitTesting(false)
                        }
                    }
                Button(discussionMode.sendLabel) {
                    Task {
                        switch discussionMode {
                        case .discuss:
                            await sendDiscussTurn(book: book)
                        case .revise:
                            await sendReviseTurn(book: book)
                        }
                    }
                }
                .disabled(userInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isPlanning)
            }
        }
    }

    // MARK: - C 动线：出初稿 / 重新生成

    /// 一键让 AI 出规划初稿（阶段 1 → 阶段 2）。
    private func generateInitialPlan(book: Book) async {
        guard !isPlanning else { return }
        isPlanning = true
        defer { isPlanning = false }
        do {
            let hint = nextChapterHint.isEmpty ? "第 \(book.chapters.count + 1) 章" : nextChapterHint
            let resp = try await core.planDraft(.init(
                book_title: book.title,
                next_chapter_hint: hint,
                context_text: await buildContextText(book: book),
                style_text: buildStyleText(book: book)
            ))
            // 把 AI 的回复作为可编辑初稿
            initialPlan = resp.assistant
            hasInitialPlan = true
            turns = []
            showDiscussion = false
            showToast("AI 已生成规划（\(initialPlan.count) 字），可直接采用或继续优化")
        } catch {
            showToast("❌ 出规划失败：\(error.localizedDescription)")
        }
    }

    private func lockCurrentPlan() {
        let trimmed = initialPlan.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        finalPlan = trimmed
        planLocked = true
        showToast("已锁定规划（\(finalPlan.count) 字）")
    }

    private func adoptCurrentPlan() {
        lockCurrentPlan()
        showToast("已采用当前规划并锁定，可点「按规划续写」出章")
    }

    /// 重新生成初稿：清空当前初稿 + 讨论历史，重新走一遍 plan_turn。
    private func regenerateInitialPlan(book: Book) async {
        initialPlan = ""
        turns = []
        userInput = ""
        showDiscussion = false
        await generateInitialPlan(book: book)
    }

    // MARK: - 续写结果面板（4 个动作都集中在这）

    @ViewBuilder
    private func resultPanel(book: Book) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // 标题（可编辑）
            TextField("章节标题", text: $generatedTitle, axis: .vertical)
                .font(.title2.bold())
                .textFieldStyle(.plain)
                .padding(.horizontal, 4)
                .help("可手动修改标题")

            // 正文（编辑 / 预览）
            HStack(spacing: 8) {
                Picker("查看", selection: $showBodyPreview) {
                    Text("编辑").tag(false)
                    Text("预览").tag(true)
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 180)
                .help(showBodyPreview ? "切回编辑模式可直接修改正文" : "切到预览模式可看到渲染后的 markdown 标题")
                Spacer()
                Text("\(generatedBody.count) 字")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            if showBodyPreview {
                renderedMarkdownView(text: generatedBody)
            } else {
                TextEditor(text: $generatedBody)
                    .font(.body)
                    .frame(minHeight: 280, maxHeight: 520)
                    .border(.separator, width: 1)
                    .help("可手动修改正文")
            }

            // 4 个动作按钮
            HStack(spacing: 8) {
                Button {
                    copyToClipboard()
                } label: {
                    Label("复制", systemImage: "doc.on.doc")
                }
                .help("把「标题 + 正文」整章复制到剪贴板")

                Button {
                    adoptIntoBook(book: book)
                } label: {
                    Label(adopted ? "已加入原文" : "采纳，加入原文", systemImage: adopted ? "checkmark.circle.fill" : "text.append")
                }
                .disabled(adopted || generatedBody.isEmpty)
                .help("把这一章追加到原文末尾（增量导入）")

                Button {
                    Task { await aiRewrite(book: book) }
                } label: {
                    Label("AI 重写", systemImage: "arrow.triangle.2.circlepath")
                }
                .disabled(generatedBody.isEmpty || isBusy)
                .help("让 AI 审稿 + 给出建议重写版")

                Button {
                    Task { await checkConsistency(book: book) }
                } label: {
                    Label("一致性检查", systemImage: "checkmark.shield")
                }
                .disabled(generatedBody.isEmpty || isBusy)
                .help("用 LLM 扫一遍与前文的冲突（人物/世界/剧情）")

                Spacer()
            }

            // AI 重写结果
            if !critiqueSummary.isEmpty || !critiqueIssues.isEmpty || !critiqueRevisedBody.isEmpty {
                Divider()
                aiRewritePanel
            }

            // 一致性检查结果
            if !consistencyIssues.isEmpty || !consistencySummary.isEmpty {
                Divider()
                consistencyPanel
            }
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }

    private var aiRewritePanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "sparkles.rectangle.stack")
                Text("AI 重写建议").font(.headline)
                Spacer()
            }
            if !critiqueSummary.isEmpty {
                Text(critiqueSummary)
                    .font(.callout)
                    .foregroundStyle(.primary)
            }
            if !critiqueIssues.isEmpty {
                ForEach(critiqueIssues) { issue in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: severityIcon(issue.severity))
                            .foregroundStyle(severityColor(issue.severity))
                            .frame(width: 16)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("[\(issue.category)] \(issue.description)")
                                .font(.subheadline.bold())
                            Text("建议：\(issue.suggestion)")
                                .font(.callout)
                                .foregroundStyle(.secondary)
                            if !issue.evidence.isEmpty {
                                Text("原文：\(issue.evidence)")
                                    .font(.caption)
                                    .foregroundStyle(.tertiary)
                                    .italic()
                            }
                        }
                    }
                }
            }
            if !critiqueRevisedBody.isEmpty {
                Divider()
                HStack {
                    Text("建议重写版（\(critiqueRevisedBody.count) 字）")
                        .font(.subheadline.bold())
                    Spacer()
                    Button("用这版替换") {
                        generatedTitle = critiqueRevisedTitle
                        generatedBody = critiqueRevisedBody
                        adopted = false  // 改了之后需要重新采纳
                        showToast("已替换为 AI 重写版")
                    }
                    .buttonStyle(.bordered)
                }
                ScrollView {
                    renderedMarkdownText(critiqueRevisedBody)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                }
                .frame(maxHeight: 320)
                .border(.separator, width: 1)
            }
        }
    }

    private var consistencyPanel: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: "checkmark.shield")
                Text("一致性检查：\(consistencySummary)").font(.headline)
                Spacer()
            }
            ForEach(consistencyIssues) { issue in
                HStack(alignment: .top) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(issue.severity == "high" ? .red : .orange)
                    VStack(alignment: .leading) {
                        Text("[\(issue.category)] \(issue.field)").font(.subheadline.bold())
                        Text(issue.description).font(.callout)
                        if !issue.evidence.isEmpty {
                            Text(issue.evidence).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
    }

    // MARK: - 4 个动作

    private func copyToClipboard() {
        let text = (generatedTitle.isEmpty ? "" : generatedTitle + "\n\n") + generatedBody
        let pb = NSPasteboard.general
        pb.clearContents()
        pb.setString(text, forType: .string)
        showToast("已复制到剪贴板（\(text.count) 字）")
    }

    private func adoptIntoBook(book: Book) {
        let chapterText = generatedTitle + "\n\n" + generatedBody
        let separator = book.rawText.isEmpty ? "" : "\n\n"
        var updated = book
        updated.rawText = book.rawText + separator + chapterText
        let nextIndex = (book.chapters.map { $0.index }.max() ?? 0) + 1
        let newChapter = CoreClient.ChapterDTO(
            index: nextIndex,
            title: generatedTitle,
            body: generatedBody,
            char_count: generatedBody.count,
            kind: "续写"
        )
        updated.chapters.append(newChapter)
        bookStore.update(updated)
        adopted = true
        showToast("已加入原文（+1 章）")
    }

    private func aiRewrite(book: Book) async {
        isBusy = true
        defer { isBusy = false }
        do {
            let resp = try await core.critique(.init(
                book_title: book.title,
                next_chapter_hint: nextChapterHint.isEmpty ? "第 \(book.chapters.count + 1) 章" : nextChapterHint,
                target_chars: targetChars,
                mode: mode.rawValue,
                final_plan: currentFinalPlan,
                history: turns,
                context_text: await buildContextText(book: book),
                style_text: buildStyleText(book: book),
                current_title: generatedTitle,
                current_draft: generatedBody
            ))
            critiqueSummary = resp.summary
            critiqueIssues = resp.issues
            critiqueRevisedTitle = resp.revised_title
            critiqueRevisedBody = resp.revised_body
        } catch {
            critiqueSummary = "❌ AI 重写失败：\(error.localizedDescription)"
            critiqueIssues = []
            critiqueRevisedBody = ""
        }
    }

    /// 拼装当前动线的 final_plan：A 必空；B 取 userPlan；C 取 finalPlan（已锁定）
    private var currentFinalPlan: String {
        switch mode {
        case .auto:
            return ""
        case .userPlan:
            return userPlan
        case .aiPlan:
            return finalPlan
        }
    }

    // MARK: - 网络（续写 / 一致性 / 规划）

    /// 讨论模式：给建议，用户手动合并。
    private func sendDiscussTurn(book: Book) async {
        let text = userInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let userTurn = CoreClient.TurnDTO(role: "user", content: text)
        turns.append(userTurn)
        userInput = ""
        await callPlanTurn(book: book, hint: nextChapterHint.isEmpty ? "第 \(book.chapters.count + 1) 章" : nextChapterHint)
    }

    /// 优化模式：AI 直接重写规划并更新编辑框。
    private func sendReviseTurn(book: Book) async {
        let text = userInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let hint = nextChapterHint.isEmpty ? "第 \(book.chapters.count + 1) 章" : nextChapterHint
        let userTurn = CoreClient.TurnDTO(role: "user", content: text)
        turns.append(userTurn)
        userInput = ""
        isPlanning = true
        defer { isPlanning = false }
        do {
            let resp = try await core.planRevise(.init(
                book_title: book.title,
                next_chapter_hint: hint,
                current_plan: initialPlan,
                user_feedback: text,
                history: turns,
                context_text: await buildContextText(book: book),
                style_text: buildStyleText(book: book)
            ))
            turns.append(.init(role: "assistant", content: resp.assistant))
            initialPlan = resp.assistant
            showToast("AI 已更新规划（\(initialPlan.count) 字）")
        } catch {
            turns.append(.init(role: "assistant", content: "❌ 优化失败：\(error.localizedDescription)"))
            showToast("❌ 优化规划失败")
        }
    }

    private func callPlanTurn(book: Book, hint: String) async {
        isPlanning = true
        defer { isPlanning = false }
        do {
            let resp = try await core.planTurn(.init(
                book_title: book.title,
                next_chapter_hint: hint,
                user_message: turns.last(where: { $0.role == "user" })?.content ?? "",
                history: turns,
                context_text: await buildContextText(book: book),
                style_text: buildStyleText(book: book)
            ))
            turns.append(.init(role: "assistant", content: resp.assistant))
        } catch {
            turns.append(.init(role: "assistant", content: "❌ 出错：\(error.localizedDescription)"))
        }
    }

    private func generate(book: Book) async {
        isBusy = true
        defer { isBusy = false }
        do {
            let resp = try await core.generate(.init(
                book_title: book.title,
                next_chapter_hint: nextChapterHint.isEmpty ? "第 \(book.chapters.count + 1) 章" : nextChapterHint,
                target_chars: targetChars,
                mode: mode.rawValue,
                final_plan: currentFinalPlan,
                history: turns,
                context_text: await buildContextText(book: book),
                style_text: buildStyleText(book: book)
            ))
            generatedTitle = resp.chapter_title
            generatedBody = resp.body
            consistencyIssues = []
            consistencySummary = ""
            critiqueSummary = ""
            critiqueIssues = []
            critiqueRevisedBody = ""
            critiqueRevisedTitle = ""
            adopted = false
            switch mode {
            case .auto:
                showToast("已生成（A 动线 · 即兴）")
            case .userPlan:
                showToast("已按你的规划生成（B 动线）")
            case .aiPlan:
                showToast("已按锁定的规划生成（C 动线）")
            }
        } catch {
            generatedBody = "❌ 生成失败：\(error.localizedDescription)"
        }
    }

    private func checkConsistency(book: Book) async {
        isBusy = true
        defer { isBusy = false }
        do {
            let resp = try await core.checkConsistency(.init(
                known_context: await buildContextText(book: book),
                new_chapter: generatedTitle + "\n\n" + generatedBody
            ))
            consistencySummary = resp.summary
            consistencyIssues = resp.issues
            if resp.is_clean {
                showToast("✅ 一致性检查通过")
            } else {
                showToast("⚠️ 发现 \(resp.issues.count) 处潜在冲突")
            }
        } catch {
            consistencySummary = "❌ 检查失败：\(error.localizedDescription)"
            consistencyIssues = []
        }
    }

    // MARK: - 拼装

    private func buildContextText(book: Book) async -> String {
        do {
            let resp = try await core.buildContext(
                summaries: book.summaries,
                totalChapters: book.chapters.count
            )
            lastContextStats = "\(resp.fine_count) 细 / \(resp.coarse_count) 粗 / \(resp.ultra_count) 极简"
            return resp.rendered
        } catch {
            let recent = Array(book.summaries.suffix(10))
            return recent.map { "【\($0.title)】\n\($0.text)" }.joined(separator: "\n\n")
        }
    }

    private func buildStyleText(book: Book) -> String {
        var parts: [String] = []
        if !book.antiAIDirective.isEmpty { parts.append(book.antiAIDirective) }
        if !book.styleDescription.isEmpty { parts.append("【原作风格】\n" + book.styleDescription) }
        return parts.joined(separator: "\n\n")
    }

    // MARK: - UI 辅助

    private func showToast(_ message: String) {
        withAnimation(.easeInOut(duration: 0.2)) { toast = message }
        Task {
            try? await Task.sleep(nanoseconds: 2_500_000_000)
            await MainActor.run {
                withAnimation(.easeInOut(duration: 0.3)) { toast = nil }
            }
        }
    }

    private func severityColor(_ severity: String) -> Color {
        switch severity {
        case "high": return .red
        case "low": return .secondary
        default: return .orange
        }
    }

    private func severityIcon(_ severity: String) -> String {
        switch severity {
        case "high": return "exclamationmark.triangle.fill"
        case "low": return "info.circle"
        default: return "exclamationmark.circle.fill"
        }
    }

    // MARK: - Markdown 渲染

    /// 把正文里的 `##` 标题、`**加粗**` 等 markdown 渲染成可视样式。
    /// 解析失败时回退到纯文本，避免内容框空白。
    private func renderedMarkdownText(_ raw: String) -> Text {
        if let attr = try? AttributedString(
            markdown: raw,
            options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .full)
        ) {
            return Text(attr)
        }
        return Text(raw)
    }

    /// 预览态下的正文容器：ScrollView + 渲染后的 Text，复用与编辑态一致的 min/maxHeight。
    private func renderedMarkdownView(text: String) -> some View {
        ScrollView {
            renderedMarkdownText(text)
                .font(.body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
        }
        .frame(minHeight: 280, maxHeight: 520)
        .background(Color(NSColor.textBackgroundColor))
        .overlay(
            RoundedRectangle(cornerRadius: 0)
                .stroke(Color.gray.opacity(0.25), lineWidth: 1)
        )
    }
}

struct ChatBubble: View {
    let role: String
    let content: String
    var assistantLabel: String = "AI"

    var body: some View {
        HStack(alignment: .top) {
            if role == "user" { Spacer() }
            VStack(alignment: role == "user" ? .trailing : .leading, spacing: 4) {
                Text(role == "user" ? "你" : assistantLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(content)
                    .padding(10)
                    .background(role == "user" ? Color.accentColor.opacity(0.18) : Color.gray.opacity(0.12))
                    .cornerRadius(8)
            }
            .frame(maxWidth: 460, alignment: role == "user" ? .trailing : .leading)
            if role != "user" { Spacer() }
        }
    }
}

/// C 动线讨论面板的两种模式。
private enum PlanDiscussionMode: String, CaseIterable, Identifiable {
    case revise   // AI 直接改写规划
    case discuss  // 给建议，用户手动合并

    var id: String { rawValue }

    var title: String {
        switch self {
        case .revise:  return "AI 优化"
        case .discuss: return "讨论建议"
        }
    }

    var sendLabel: String {
        switch self {
        case .revise:  return "AI 优化"
        case .discuss: return "发送"
        }
    }

    var assistantLabel: String {
        switch self {
        case .revise:  return "AI 规划"
        case .discuss: return "AI 建议"
        }
    }

    var hint: String {
        switch self {
        case .revise:
            return "描述你想怎么改，AI 会直接输出新版完整规划并更新上方编辑框。"
        case .discuss:
            return "和 AI 讨论剧情方向，AI 只给建议；你需要手动把改动合并回上方「规划初稿」。"
        }
    }

    var placeholder: String {
        switch self {
        case .revise:
            return "例如：把反杀改成智取 / 节奏再快一点 / 加一个身份暴露前的铺垫"
        case .discuss:
            return "例如：这个爽点会不会太刻意？有没有更自然的写法？"
        }
    }
}
