import Foundation

/// 轻量 HTTP 客户端，调用 Python sidecar 暴露的 REST API。
@MainActor
final class CoreClient: ObservableObject {
    let baseURL: URL
    private let session: URLSession

    init(baseURL: URL) {
        self.baseURL = baseURL
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 600
        cfg.timeoutIntervalForResource = 1200
        self.session = URLSession(configuration: cfg)
    }

    // MARK: - 健康

    func health() async throws -> [String: Any] {
        let url = baseURL.appendingPathComponent("health")
        let (data, resp) = try await session.data(from: url)
        try Self.assertOK(resp, data: data)
        return (try JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    // MARK: - 导入

    struct ChapterDTO: Codable, Identifiable, Hashable {
        let index: Int
        let title: String
        let body: String
        let char_count: Int
        let kind: String
        var id: Int { index }
    }

    struct ImportResponse: Codable {
        let book_title: String
        let author: String
        let char_count: Int
        let chapters: [ChapterDTO]
    }

    func importFromPaste(text: String, title: String, author: String) async throws -> ImportResponse {
        let url = baseURL.appendingPathComponent("ingest/paste")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let payload: [String: Any] = ["text": text, "title": title, "author": author]
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (data, resp) = try await session.data(for: req)
        try Self.assertOK(resp, data: data)
        return try JSONDecoder().decode(ImportResponse.self, from: data)
    }

    func importFromPath(_ path: String) async throws -> ImportResponse {
        let url = baseURL.appendingPathComponent("ingest/path")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["path": path])
        let (data, resp) = try await session.data(for: req)
        try Self.assertOK(resp, data: data)
        return try JSONDecoder().decode(ImportResponse.self, from: data)
    }

    // MARK: - 摘要

    struct SummaryDTO: Codable, Identifiable, Hashable {
        let chapter_index: Int
        let title: String
        let tier: String
        let text: String
        var id: Int { chapter_index }
    }

    struct SummarizeResponse: Codable {
        let summaries: [SummaryDTO]
    }

    /// 摘要。`indices` 非空时只摘要这些 index（其余过滤掉），空 = 全部。
    /// `tier`: "fine" | "coarse" | "ultra" | "all"（"all" 一次生成三档）
    func summarize(bookTitle: String, chapters: [ChapterDTO], tier: String, indices: [Int]? = nil) async throws -> SummarizeResponse {
        let url = baseURL.appendingPathComponent("summarize")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var payload: [String: Any] = [
            "book_title": bookTitle,
            "chapters": chapters.map { ["index": $0.index, "title": $0.title, "body": $0.body, "char_count": $0.char_count, "kind": $0.kind] },
            "tier": tier,
        ]
        if let indices = indices, !indices.isEmpty {
            payload["indices"] = indices
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (data, resp) = try await session.data(for: req)
        try Self.assertOK(resp, data: data)
        return try JSONDecoder().decode(SummarizeResponse.self, from: data)
    }

    // MARK: - Analyze（一步：风格 + 三档摘要）

    struct AnalyzeRequest: Codable {
        let book_title: String
        let chapters: [ChapterDTO]
        let indices: [Int]?
    }

    struct AnalyzeResponse: Codable {
        let style_description: String
        let anti_ai_directive: String
        let style_samples: [String]
        let summaries: [SummaryDTO]
    }

    /// 一步完成风格 + 三档摘要。`indices` 非空时只摘要这些 index（增量），风格仍按全书。
    func analyze(bookTitle: String, chapters: [ChapterDTO], indices: [Int]? = nil) async throws -> AnalyzeResponse {
        let url = baseURL.appendingPathComponent("analyze")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let payload: [String: Any] = [
            "book_title": bookTitle,
            "chapters": chapters.map { ["index": $0.index, "title": $0.title, "body": $0.body, "char_count": $0.char_count, "kind": $0.kind] },
            "indices": indices as Any,
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (data, resp) = try await session.data(for: req)
        try Self.assertOK(resp, data: data)
        return try JSONDecoder().decode(AnalyzeResponse.self, from: data)
    }

    // MARK: - 上下文滑动窗口

    struct ContextBuildRequest: Codable {
        let summaries: [SummaryDTO]
        let total_chapters: Int
    }

    struct ContextBuildResponse: Codable {
        let rendered: String
        let fine_count: Int
        let coarse_count: Int
        let ultra_count: Int
    }

    /// 把 summaries 按窗口策略（最近 N 章 fine / 中期 coarse / 远端 ultra）拼成 prompt 字符串。
    func buildContext(summaries: [SummaryDTO], totalChapters: Int) async throws -> ContextBuildResponse {
        let url = baseURL.appendingPathComponent("context/build")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let payload: [String: Any] = [
            "summaries": summaries.map { ["chapter_index": $0.chapter_index, "title": $0.title, "tier": $0.tier, "text": $0.text] },
            "total_chapters": totalChapters,
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (data, resp) = try await session.data(for: req)
        try Self.assertOK(resp, data: data)
        return try JSONDecoder().decode(ContextBuildResponse.self, from: data)
    }

    // MARK: - 续写

    struct PlanTurnRequest: Codable {
        let book_title: String
        let next_chapter_hint: String
        let user_message: String
        let history: [TurnDTO]
        let context_text: String
        let style_text: String
    }

    struct TurnDTO: Codable {
        let role: String
        let content: String
    }

    struct PlanTurnResponse: Codable {
        let assistant: String
    }

    func planTurn(_ req: PlanTurnRequest) async throws -> PlanTurnResponse {
        try await post("/continue/plan_turn", body: req)
    }

    struct PlanDraftRequest: Codable {
        let book_title: String
        let next_chapter_hint: String
        let context_text: String
        let style_text: String
    }

    struct PlanReviseRequest: Codable {
        let book_title: String
        let next_chapter_hint: String
        let current_plan: String
        let user_feedback: String
        let history: [TurnDTO]
        let context_text: String
        let style_text: String
    }

    /// C 动线：一键生成完整规划初稿（5 维结构化，非聊天模式）。
    func planDraft(_ req: PlanDraftRequest) async throws -> PlanTurnResponse {
        try await post("/continue/plan_draft", body: req)
    }

    /// C 动线：根据用户反馈直接重写规划（返回新版完整规划文本）。
    func planRevise(_ req: PlanReviseRequest) async throws -> PlanTurnResponse {
        try await post("/continue/plan_revise", body: req)
    }

    struct ContinueGenerateRequest: Codable {
        let book_title: String
        let next_chapter_hint: String
        let target_chars: Int
        // PRD F10：续写动线。"auto" / "user_plan" / "ai_plan"
        let mode: String
        let final_plan: String
        let history: [TurnDTO]
        let context_text: String
        let style_text: String
    }

    struct ContinueGenerateResponse: Codable {
        let chapter_title: String
        let body: String
        let char_count: Int
        // "stop" = 自然结束；"length" = 仍被 max_tokens 截断（侧车已尝试自动续写）
        let finish_reason: String?
    }

    /// 续写动线（PRD F10a/b/c）。与 sidecar 的 ContinueMode 一一对应。
    enum ContinueMode: String, CaseIterable, Identifiable {
        case auto      = "auto"       // A 动线：一键续写
        case userPlan  = "user_plan"  // B 动线：用户规划续写
        case aiPlan    = "ai_plan"    // C 动线：AI 规划续写

        var id: String { rawValue }

        var title: String {
            switch self {
            case .auto:     return "一键续写"
            case .userPlan: return "按我的规划续写"
            case .aiPlan:   return "AI 规划续写"
            }
        }

        var subtitle: String {
            switch self {
            case .auto:
                return "不规划，AI 基于上下文即兴"
            case .userPlan:
                return "我先填规划，AI 严格按规划写"
            case .aiPlan:
                return "AI 先出规划，多轮讨论后 AI 写"
            }
        }

        var systemImage: String {
            switch self {
            case .auto:     return "wand.and.stars"
            case .userPlan: return "list.bullet.rectangle"
            case .aiPlan:   return "bubble.left.and.bubble.right"
            }
        }
    }

    func generate(_ req: ContinueGenerateRequest) async throws -> ContinueGenerateResponse {
        try await post("/continue/generate", body: req)
    }

    // MARK: - 一致性

    struct ConsistencyRequest: Codable {
        let known_context: String
        let new_chapter: String
    }

    struct ConsistencyIssueDTO: Codable, Identifiable {
        let category: String
        let field: String
        let description: String
        let severity: String
        let evidence: String
        var id: String { "\(category)-\(field)-\(description.hashValue)" }
    }

    struct ConsistencyResponse: Codable {
        let is_clean: Bool
        let summary: String
        let issues: [ConsistencyIssueDTO]
    }

    func checkConsistency(_ req: ConsistencyRequest) async throws -> ConsistencyResponse {
        try await post("/consistency/check", body: req)
    }

    // MARK: - AI 重写：修改意见 + 建议重写版

    struct CritiqueRequest: Codable {
        let book_title: String
        let next_chapter_hint: String
        let target_chars: Int
        let mode: String
        let final_plan: String
        let history: [TurnDTO]
        let context_text: String
        let style_text: String
        let current_title: String
        let current_draft: String
    }

    struct CritiqueIssueDTO: Codable, Identifiable, Hashable {
        let category: String
        let severity: String
        let description: String
        let suggestion: String
        let evidence: String
        var id: String { "\(category)-\(severity)-\(description.hashValue)" }
    }

    struct CritiqueResponse: Codable {
        let summary: String
        let issues: [CritiqueIssueDTO]
        let revised_title: String
        let revised_body: String
        let char_count: Int
    }

    func critique(_ req: CritiqueRequest) async throws -> CritiqueResponse {
        try await post("/continue/critique", body: req)
    }

    // MARK: - helpers

    private func post<Req: Encodable, Resp: Decodable>(_ path: String, body: Req) async throws -> Resp {
        let url = baseURL.appendingPathComponent(path)
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let (data, resp) = try await session.data(for: req)
        try Self.assertOK(resp, data: data)
        return try JSONDecoder().decode(Resp.self, from: data)
    }

    private static func assertOK(_ resp: URLResponse, data: Data) throws {
        guard let http = resp as? HTTPURLResponse else {
            throw NSError(domain: "NextChapter", code: -1, userInfo: [NSLocalizedDescriptionKey: "无效响应"])
        }
        guard (200..<300).contains(http.statusCode) else {
            let snippet = String(data: data, encoding: .utf8) ?? ""
            throw NSError(
                domain: "NextChapter", code: http.statusCode,
                userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode): \(snippet.prefix(200))"]
            )
        }
    }
}
