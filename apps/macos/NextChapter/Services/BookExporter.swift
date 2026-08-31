import Foundation
import AppKit
import UniformTypeIdentifiers

/// 把 Book 渲染成干净的全书 TXT，并弹出 NSSavePanel 写入。
///
/// 输出格式：
/// ```
/// 《书名》
/// 作者：xxx
///
/// 第一章 标题
///
/// 正文...
///
/// 第二章 标题
///
/// 正文...
/// ```
///
/// 章节按 `chapters[].index` 升序输出（含续写章节，与用户在详情页看到的顺序一致）。
enum BookExporter {

    // MARK: - 渲染

    /// 把整本书拼成 TXT 字符串。空章节列表返回只有元信息的最小文本。
    static func renderTXT(_ book: Book) -> String {
        let title = book.title.isEmpty ? "未命名作品" : book.title
        let author = book.author.isEmpty ? "佚名" : book.author

        var lines: [String] = []
        lines.append("《\(title)》")
        lines.append("作者：\(author)")
        lines.append("")  // 元信息块末尾空一行
        lines.append("")

        let sorted = book.chapters.sorted { $0.index < $1.index }
        for (i, ch) in sorted.enumerated() {
            if i > 0 {
                // 章节之间空两行（一个空行作为分隔，等价于「标题前留一空行」）
                lines.append("")
                lines.append("")
            }
            lines.append(ch.title)
            lines.append("")
            lines.append(ch.body)
        }
        return lines.joined(separator: "\n")
    }

    /// 默认导出文件名：`<书名>.txt`，剔除 macOS 文件系统非法字符 `/ \ : ? * " < > |`。
    static func suggestFilename(_ book: Book) -> String {
        let base = book.title.isEmpty ? "未命名作品" : book.title
        let invalid = CharacterSet(charactersIn: "/\\:?*\"<>|")
        let cleanedScalars = base.unicodeScalars.filter { !invalid.contains($0) }
        let cleaned = String(String.UnicodeScalarView(cleanedScalars))
        let trimmed = cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
        let safe = trimmed.isEmpty ? "未命名作品" : trimmed
        return safe + ".txt"
    }

    // MARK: - 写入

    /// 弹出 NSSavePanel，让用户选位置并写入 UTF-8 TXT。
    /// - Returns: 成功写入返回文件 URL；用户取消或写入失败返回 `nil`。
    @MainActor
    @discardableResult
    static func saveTXTWithPanel(_ book: Book) -> URL? {
        let panel = NSSavePanel()
        panel.title = "导出「\(book.title.isEmpty ? "未命名作品" : book.title)」为 TXT"
        panel.allowedContentTypes = [.plainText]
        panel.nameFieldStringValue = suggestFilename(book)
        panel.canCreateDirectories = true
        panel.isExtensionHidden = false
        // 允许在文件名里不带扩展名时自动补 .txt
        panel.allowsOtherFileTypes = false

        guard panel.runModal() == .OK, let url = panel.url else { return nil }
        do {
            let text = renderTXT(book)
            try text.write(to: url, atomically: true, encoding: .utf8)
            return url
        } catch {
            let alert = NSAlert()
            alert.messageText = "导出失败"
            alert.informativeText = error.localizedDescription
            alert.alertStyle = .warning
            alert.addButton(withTitle: "好")
            alert.runModal()
            return nil
        }
    }
}
