import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct LibraryView: View {
    @EnvironmentObject private var core: CoreClient
    @EnvironmentObject private var bookStore: BookStore
    @Binding var selectedBookId: String?
    @Binding var importError: String?
    @Binding var isImporting: Bool
    @State private var showPasteSheet = false
    @State private var showFileImporter = false
    @State private var pasteText = ""
    @State private var pasteTitle = ""
    @State private var showDeleteConfirm = false
    @State private var bookToDelete: Book?

    var body: some View {
        NavigationSplitView {
            sidebar
        } detail: {
            detail
        }
        .toolbar { toolbar }
        .fileImporter(
            isPresented: $showFileImporter,
            allowedContentTypes: txtContentTypes,
            allowsMultipleSelection: false
        ) { result in
            handleFileImport(result)
        }
        .sheet(isPresented: $showPasteSheet) {
            pasteSheet
        }
        .confirmationDialog(
            "确认删除「\(bookToDelete?.title ?? "")」？",
            isPresented: $showDeleteConfirm,
            titleVisibility: .visible,
            presenting: bookToDelete
        ) { book in
            Button("删除", role: .destructive) {
                if selectedBookId == book.id { selectedBookId = nil }
                bookStore.remove(id: book.id)
                bookToDelete = nil
            }
            Button("取消", role: .cancel) {
                bookToDelete = nil
            }
        } message: { _ in
            Text("该作品的章节、摘要、风格档案会一并移除。此操作不可撤销。")
        }
        .alert("导入失败", isPresented: errorBinding) {
            Button("好") { importError = nil }
        } message: {
            Text(importError ?? "")
        }
    }

    // MARK: - 子视图

    private var sidebar: some View {
        List(selection: $selectedBookId) {
            Section("我的书库") {
                if bookStore.books.isEmpty {
                    Text("暂无作品")
                        .foregroundStyle(.secondary)
                        .font(.callout)
                } else {
                    ForEach(bookStore.books) { book in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(book.title)
                                .font(.headline)
                                .lineLimit(1)
                            HStack {
                                Text(book.author.isEmpty ? "佚名" : book.author)
                                Text("·")
                                Text("\(book.chapters.count) 章")
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        }
                        .tag(book.id)
                        .contextMenu {
                            Button {
                                _ = BookExporter.saveTXTWithPanel(book)
                            } label: {
                                Label("导出 TXT…", systemImage: "square.and.arrow.up")
                            }
                            .disabled(book.chapters.isEmpty)
                            Divider()
                            Button("删除", role: .destructive) {
                                bookToDelete = book
                                showDeleteConfirm = true
                            }
                        }
                    }
                }
            }
        }
        .frame(minWidth: 240)
    }

    @ViewBuilder
    private var detail: some View {
        if let id = selectedBookId, let book = bookStore.books.first(where: { $0.id == id }) {
            BookDetailView(book: book)
        } else {
            VStack(spacing: 20) {
                Image("AppLogo")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 360, height: 196)
                    .opacity(0.85)
                Text("选择或导入一部作品开始")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                Text("从左侧选择作品，或点击工具栏的「文档导入 / 粘贴导入」。")
                    .font(.callout)
                    .foregroundStyle(.tertiary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            Button {
                showFileImporter = true
            } label: {
                Label("文档导入", systemImage: "doc.text")
            }
            .help("从本地 TXT 文件导入")
            .disabled(isImporting)
            Button {
                showPasteSheet = true
            } label: {
                Label("粘贴导入", systemImage: "doc.on.clipboard")
            }
            .help("直接粘贴整本或新增章节")
            .disabled(isImporting)
            if selectedBookId != nil,
               let id = selectedBookId,
               bookStore.books.contains(where: { $0.id == id }) {
                Button(role: .destructive) {
                    if let book = bookStore.books.first(where: { $0.id == id }) {
                        bookToDelete = book
                        showDeleteConfirm = true
                    }
                } label: {
                    Label("删除", systemImage: "trash")
                }
                .help("从书库移除当前选中的作品")
            }
        }
    }

    private var pasteSheet: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("粘贴导入").font(.title2.bold())
            TextField("作品名（留空时尝试自动识别）", text: $pasteTitle)
            Text("将正文粘贴到下方：")
                .foregroundStyle(.secondary)
            TextEditor(text: $pasteText)
                .frame(minHeight: 240)
                .border(.separator, width: 1)
            HStack {
                Spacer()
                Button("取消") { showPasteSheet = false; pasteText = ""; pasteTitle = "" }
                    .keyboardShortcut(.cancelAction)
                Button("导入") { Task { await importPaste() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(pasteText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(20)
        .frame(minWidth: 560, minHeight: 420)
    }

    // MARK: - 操作

    /// fileImporter 允许的文件类型：纯文本 + .txt 扩展名。
    private var txtContentTypes: [UTType] {
        var types: [UTType] = [.plainText]
        if let ext = UTType(filenameExtension: "txt") {
            types.append(ext)
        }
        return types
    }

    /// 读取本地 TXT，兼容 UTF-8 / UTF-16 / GB18030（覆盖常见老中文编码）。
    private func readLocalText(_ url: URL) -> String {
        let needAccess = url.startAccessingSecurityScopedResource()
        defer { if needAccess { url.stopAccessingSecurityScopedResource() } }
        // 1) 自动检测（基于 BOM / 启发式，覆盖 UTF-8 / UTF-16）
        if let s = try? String(contentsOf: url) {
            return s
        }
        // 2) 显式编码 fallback：GB18030 覆盖 GBK / GB2312
        //    NSString encoding for GB_18030_2000 = 0x80000632
        let raw = (try? Data(contentsOf: url)) ?? Data()
        let encodings: [String.Encoding] = [
            .utf8,
            .utf16,
            String.Encoding(rawValue: 0x80000632),
        ]
        for enc in encodings {
            if let s = String(data: raw, encoding: enc) {
                return s
            }
        }
        return ""
    }

    private func handleFileImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            Task { await importPath(url) }
        case .failure(let err):
            // 用户取消也会走这里，但 NSError 用户域是 NSCocoaErrorDomain 且 code == NSUserCancelledError
            let nsErr = err as NSError
            if nsErr.domain == "NSCocoaErrorDomain" && nsErr.code == NSUserCancelledError {
                return
            }
            importError = err.localizedDescription
        }
    }

    private func importPath(_ url: URL) async {
        isImporting = true
        defer { isImporting = false }
        do {
            let resp = try await core.importFromPath(url.path)
            let raw = readLocalText(url)
            if raw.isEmpty {
                importError = "读取文件内容失败：\(url.lastPathComponent)（可能编码不被支持）"
                return
            }
            let book = Book(
                title: resp.book_title,
                author: resp.author,
                rawText: raw,
                chapters: resp.chapters
            )
            bookStore.add(book)
            selectedBookId = book.id
        } catch {
            importError = "导入失败：\(error.localizedDescription)"
        }
    }

    private func importPaste() async {
        isImporting = true
        defer { isImporting = false }
        do {
            let resp = try await core.importFromPaste(
                text: pasteText,
                title: pasteTitle.isEmpty ? "未命名作品" : pasteTitle,
                author: ""
            )
            let book = Book(
                title: resp.book_title,
                author: resp.author,
                rawText: pasteText,
                chapters: resp.chapters
            )
            bookStore.add(book)
            selectedBookId = book.id
            showPasteSheet = false
            pasteText = ""
            pasteTitle = ""
        } catch {
            importError = "导入失败：\(error.localizedDescription)"
        }
    }

    private var errorBinding: Binding<Bool> {
        Binding(get: { importError != nil }, set: { if !$0 { importError = nil } })
    }
}
