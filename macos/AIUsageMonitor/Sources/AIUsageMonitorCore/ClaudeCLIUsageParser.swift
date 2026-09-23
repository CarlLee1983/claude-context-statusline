import Foundation

/// Parses Claude Code's local `/usage` command result. Only the two general
/// subscription windows are used; contribution percentages are unrelated.
public enum ClaudeCLIUsageParser {
    public static func parse(_ data: Data, now: Date = .now) -> [UsageWindow] {
        guard
            let response = try? JSONDecoder().decode(Response.self, from: data),
            response.localCommand == "usage",
            !response.isError
        else { return [] }

        let lines = response.result.split(whereSeparator: \.isNewline)
        var windows: [UsageWindow] = []
        for (prefix, label, horizon) in [
            ("Current session:", "5h", 5 * 3_600.0),
            ("Current week (all models):", "7d", 7 * 24 * 3_600.0),
        ] {
            guard let line = lines.first(where: { $0.hasPrefix(prefix) }) else { continue }
            let remainder = line.dropFirst(prefix.count).trimmingCharacters(in: .whitespaces)
            guard let match = firstMatch(#"^([0-9]+(?:\.[0-9]+)?)% used(?: · resets (.+))?$"#, in: remainder),
                  let percentText = capture(1, from: match, in: remainder),
                  let percent = Double(percentText)
            else { continue }

            let reset = capture(2, from: match, in: remainder)
                .flatMap { parseReset($0, now: now, horizon: horizon) }
            windows.append(UsageWindow(label: label, percent: percent, kind: .used, resetAt: reset))
        }
        return windows
    }

    private static func parseReset(_ text: String, now: Date, horizon: TimeInterval) -> Date? {
        guard
            let match = firstMatch(#"^([A-Z][a-z]{2}) (\d{1,2}) at (\d{1,2}):(\d{2})(am|pm) \(([^)]+)\)$"#, in: text),
            let monthText = capture(1, from: match, in: text),
            let month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                .firstIndex(of: monthText).map({ $0 + 1 }),
            let dayText = capture(2, from: match, in: text), let day = Int(dayText),
            let hourText = capture(3, from: match, in: text), let hour = Int(hourText), (1...12).contains(hour),
            let minuteText = capture(4, from: match, in: text), let minute = Int(minuteText), (0...59).contains(minute),
            let meridiem = capture(5, from: match, in: text),
            let zoneName = capture(6, from: match, in: text), let zone = TimeZone(identifier: zoneName)
        else { return nil }

        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = zone
        let year = calendar.component(.year, from: now)
        let hour24 = hour % 12 + (meridiem == "pm" ? 12 : 0)
        for candidateYear in [year, year + 1] {
            guard let date = calendar.date(from: DateComponents(
                year: candidateYear, month: month, day: day, hour: hour24, minute: minute
            )) else { continue }
            // The reset belongs to the current 5h or 7d window. A small
            // tolerance covers display rounding and clock skew.
            let delta = date.timeIntervalSince(now)
            if delta >= -120 && delta <= horizon + 3_600 { return date }
        }
        return nil
    }

    private static func firstMatch(_ pattern: String, in text: String) -> NSTextCheckingResult? {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        return regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text))
    }

    private static func capture(_ index: Int, from match: NSTextCheckingResult, in text: String) -> String? {
        guard let range = Range(match.range(at: index), in: text) else { return nil }
        return String(text[range])
    }

    private struct Response: Decodable {
        let isError: Bool
        let localCommand: String
        let result: String

        enum CodingKeys: String, CodingKey {
            case isError = "is_error"
            case localCommand = "local_command"
            case result
        }
    }
}
