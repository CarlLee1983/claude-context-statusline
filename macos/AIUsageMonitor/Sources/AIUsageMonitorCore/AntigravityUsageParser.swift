import Foundation

public enum AntigravityUsageParser {
    public static func parse(_ rawText: String) -> [UsageWindow] {
        var text = rawText.replacingOccurrences(of: "\r", with: "\n")
        if let range = text.range(of: "Model Quota", options: .backwards) {
            text = String(text[range.lowerBound...])
        }

        let lines = text
            .components(separatedBy: .newlines)
            .map { stripANSI($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        var windows: [UsageWindow] = []
        for (index, line) in lines.enumerated() {
            if shouldSkip(line) || line.contains("█") || line.contains("░") || line.contains("%") {
                continue
            }

            let lookahead = lines.dropFirst(index + 1).prefix(3)
            guard let percent = firstPercent(in: lookahead) else { continue }
            windows.append(UsageWindow(label: line, percent: percent, kind: .available))
        }
        return windows
    }

    private static func shouldSkip(_ line: String) -> Bool {
        line == "Model Quota" ||
            line == "Quota available" ||
            line.hasSuffix("Model Quota") ||
            line.localizedCaseInsensitiveContains("shortcuts") ||
            line.localizedCaseInsensitiveContains("scroll") ||
            line.localizedCaseInsensitiveContains("esc")
    }

    private static func firstPercent<S: Sequence>(in lines: S) -> Double? where S.Element == String {
        for line in lines {
            if let match = line.range(of: #"(\d+(?:\.\d+)?)\s*%"#, options: .regularExpression) {
                let token = line[match]
                    .replacingOccurrences(of: "%", with: "")
                    .trimmingCharacters(in: .whitespaces)
                return Double(token)
            }
        }
        return nil
    }

    // ESC char built via Swift escape so the literal ESC byte (not the text
    // "\u{001B}") reaches the ICU regex engine. Covers CSI sequences (colors,
    // erase-line), private-mode sets, and a catch-all for 2-byte escapes —
    // mirrors the reference SwiftBar `ANSI_RE`.
    private static let ansiPattern =
        "\u{1B}\\[[0-?]*[ -/]*[@-~]|\u{1B}[>=][^A-Za-z]*[A-Za-z]?|\u{1B}\\\\?."

    private static func stripANSI(_ line: String) -> String {
        line.replacingOccurrences(of: ansiPattern, with: "", options: .regularExpression)
    }
}
