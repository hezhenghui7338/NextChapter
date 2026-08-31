import Foundation

/// 已导入到本地的小说（一本书 = 一个 project）。
struct Book: Identifiable, Codable, Equatable {
    let id: String
    var title: String
    var author: String
    var rawText: String          // 原始正文（用于增量导入）
    var chapters: [CoreClient.ChapterDTO]
    var summaries: [CoreClient.SummaryDTO]
    var styleDescription: String
    var antiAIDirective: String
    var styleSamples: [String]
    var createdAt: Date
    var updatedAt: Date

    init(id: String = UUID().uuidString, title: String, author: String, rawText: String, chapters: [CoreClient.ChapterDTO]) {
        self.id = id
        self.title = title
        self.author = author
        self.rawText = rawText
        self.chapters = chapters
        self.summaries = []
        self.styleDescription = ""
        self.antiAIDirective = ""
        self.styleSamples = []
        let now = Date()
        self.createdAt = now
        self.updatedAt = now
    }

    /// 已摘要的章节数（按 chapter_index 去重，不论 tier）。
    /// 注意：summaries 里同一章会存 fine / coarse / ultra 三条，直接用 summaries.count 会得到 3 倍数。
    var summarizedChapterCount: Int {
        Set(summaries.map { $0.chapter_index }).count
    }
}

/// 本地书库（简单 JSON 落盘）。
@MainActor
final class BookStore: ObservableObject {
    @Published var books: [Book] = []

    private let storageURL: URL

    init() {
        let appSupport = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first ?? FileManager.default.temporaryDirectory
        let dir = appSupport.appendingPathComponent("NextChapter", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        self.storageURL = dir.appendingPathComponent("books.json")
        load()
    }

    func load() {
        guard let data = try? Data(contentsOf: storageURL) else { return }
        if let decoded = try? JSONDecoder().decode([Book].self, from: data) {
            self.books = decoded
        }
    }

    func save() {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? encoder.encode(books) {
            try? data.write(to: storageURL)
        }
    }

    func add(_ book: Book) {
        books.append(book)
        save()
    }

    func update(_ book: Book) {
        if let idx = books.firstIndex(where: { $0.id == book.id }) {
            var b = book
            b.updatedAt = Date()
            books[idx] = b
            save()
        }
    }

    func remove(id: String) {
        books.removeAll { $0.id == id }
        save()
    }
}
