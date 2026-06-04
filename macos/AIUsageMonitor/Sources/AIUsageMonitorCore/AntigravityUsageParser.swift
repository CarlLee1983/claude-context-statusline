import Foundation

public enum AntigravityUsageParser {
    public static func parse(_ rawText: String, now: Date = .now) -> [UsageWindow] {
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

            let lookahead = Array(lines.dropFirst(index + 1).prefix(3))
            guard let percent = firstPercent(in: lookahead) else { continue }
            // The "… · Refreshes in 2h 46m" line gives a countdown for partially
            // used windows; turn it into an absolute reset instant. Full windows
            // show "Quota available" instead, so resetAt stays nil.
            let resetAt = firstRefreshInterval(in: lookahead).map { now.addingTimeInterval($0) }
            windows.append(UsageWindow(label: line, percent: percent, kind: .available, resetAt: resetAt))
        }
        return windows
    }

    /// Parses an Antigravity "Refreshes in …" countdown into seconds. Accepts the
    /// `1d 3h 46m 30s` token style (any subset, in any order); returns nil when no
    /// countdown is present (e.g. a "Quota available" line).
    private static func firstRefreshInterval<S: Sequence>(in lines: S) -> TimeInterval?
    where S.Element == String {
        for line in lines {
            guard let range = line.range(of: "Refreshes in", options: .caseInsensitive) else { continue }
            let tail = line[range.upperBound...]
            let units: [(suffix: String, seconds: Double)] = [
                ("d", 86_400), ("h", 3_600), ("m", 60), ("s", 1),
            ]
            var total: TimeInterval = 0
            var matched = false
            for (suffix, seconds) in units {
                let pattern = "(\\d+(?:\\.\\d+)?)\\s*" + suffix + "\\b"
                if let match = tail.range(of: pattern, options: .regularExpression) {
                    let number = tail[match].replacingOccurrences(
                        of: "[^0-9.]", with: "", options: .regularExpression
                    )
                    if let value = Double(number) {
                        total += value * seconds
                        matched = true
                    }
                }
            }
            if matched { return total }
        }
        return nil
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
    // erase-line), private-mode sets, and a catch-all for 2-byte escapes.
    private static let ansiPattern =
        "\u{1B}\\[[0-?]*[ -/]*[@-~]|\u{1B}[>=][^A-Za-z]*[A-Za-z]?|\u{1B}\\\\?."

    private static func stripANSI(_ line: String) -> String {
        line.replacingOccurrences(of: ansiPattern, with: "", options: .regularExpression)
    }
}
