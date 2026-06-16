import Foundation

public enum AntigravityUsageParser {
    /// One model group in the `agy /usage` panel (e.g. "Gemini",
    /// "Claude & GPT") with its named limit windows (Weekly / Five Hour).
    public struct ParsedGroup: Equatable, Sendable {
        public let title: String
        public let windows: [UsageWindow]

        public init(title: String, windows: [UsageWindow]) {
            self.title = title
            self.windows = windows
        }
    }

    public static func parse(_ rawText: String, now: Date = .now) -> [ParsedGroup] {
        var text = rawText.replacingOccurrences(of: "\r", with: "\n")
        // Anchor at the panel heading; tolerate the legacy "Model Quota" wording.
        if let range = text.range(of: "Models & Quota", options: .backwards) {
            text = String(text[range.lowerBound...])
        } else if let range = text.range(of: "Model Quota", options: .backwards) {
            text = String(text[range.lowerBound...])
        }

        let lines = text
            .components(separatedBy: .newlines)
            .map { stripANSI($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        var groups: [ParsedGroup] = []
        var currentTitle: String?
        var currentWindows: [UsageWindow] = []

        func flush() {
            if let title = currentTitle, !currentWindows.isEmpty {
                groups.append(ParsedGroup(title: title, windows: currentWindows))
            }
            currentWindows = []
        }

        for (index, line) in lines.enumerated() {
            if let groupName = groupTitle(from: line) {
                flush()
                currentTitle = groupName
                continue
            }
            // Limit windows only exist inside a group.
            guard currentTitle != nil else { continue }
            if shouldSkip(line) || isBarOrPercentLine(line) { continue }

            // The bar line ("[…] 77.05%") sits immediately below the limit name;
            // the "… Refreshes in" countdown is the line after it.
            let lookahead = Array(lines.dropFirst(index + 1).prefix(2))
            guard let percent = firstPercent(in: lookahead) else { continue }
            let resetAt = firstRefreshInterval(in: lookahead).map { now.addingTimeInterval($0) }
            currentWindows.append(
                UsageWindow(label: line, percent: percent, kind: .available, resetAt: resetAt)
            )
        }
        flush()
        return groups
    }

    /// A group header is an all-caps line (with letters) ending in "MODELS".
    /// Maps the two known headers to friendly names; title-cases the rest.
    private static func groupTitle(from line: String) -> String? {
        guard
            line == line.uppercased(),
            line.rangeOfCharacter(from: .letters) != nil,
            line.hasSuffix("MODELS")
        else { return nil }

        switch line {
        case "GEMINI MODELS":
            return "Gemini"
        case "CLAUDE AND GPT MODELS":
            return "Claude & GPT"
        default:
            let stripped = line.replacingOccurrences(of: "MODELS", with: "")
                .trimmingCharacters(in: .whitespaces)
            return (stripped.isEmpty ? line : stripped).capitalized
        }
    }

    private static func isBarOrPercentLine(_ line: String) -> Bool {
        line.contains("█") || line.contains("░") || line.contains("%")
            || line.contains("[") || line.contains("]")
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
        line == "Model Quota"
            || line == "Models & Quota"
            || line == "Quota available"
            || line.hasSuffix("Model Quota")
            || line.hasSuffix("Models & Quota")
            || line.localizedCaseInsensitiveContains("models within this group")
            || line.localizedCaseInsensitiveContains("account:")
            || line.localizedCaseInsensitiveContains("shortcuts")
            || line.localizedCaseInsensitiveContains("scroll")
            || line.localizedCaseInsensitiveContains("esc")
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
