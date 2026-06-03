import Foundation

/// Parses the Anthropic OAuth usage endpoint payload into `.used` usage windows.
/// Pure and total: any malformed or missing data yields an empty array.
public enum ClaudeUsageParser {
    // ISO8601DateFormatter's date(from:) is thread-safe for reads; sharing the
    // instances avoids per-call allocation. The live API returns fractional
    // seconds (e.g. "2026-06-03T06:19:59.866880+00:00"), which the default
    // formatter rejects — so try a fractional-aware formatter first and fall
    // back to the plain one for whole-second timestamps.
    private nonisolated(unsafe) static let iso8601Fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
    private nonisolated(unsafe) static let iso8601 = ISO8601DateFormatter()

    private static func parseDate(_ string: String) -> Date? {
        iso8601Fractional.date(from: string) ?? iso8601.date(from: string)
    }

    public static func parse(_ data: Data) -> [UsageWindow] {
        guard let decoded = try? JSONDecoder().decode(Response.self, from: data) else {
            return []
        }
        var windows: [UsageWindow] = []
        if let window = makeWindow(label: "5h", node: decoded.fiveHour) { windows.append(window) }
        if let window = makeWindow(label: "7d", node: decoded.sevenDay) { windows.append(window) }
        return windows
    }

    private static func makeWindow(label: String, node: Window?) -> UsageWindow? {
        guard let node else { return nil }
        return UsageWindow(
            label: label,
            percent: node.utilization,
            kind: .used,
            resetAt: Self.parseDate(node.resetsAt)
        )
    }

    private struct Response: Decodable {
        let fiveHour: Window?
        let sevenDay: Window?

        enum CodingKeys: String, CodingKey {
            case fiveHour = "five_hour"
            case sevenDay = "seven_day"
        }
    }

    private struct Window: Decodable {
        let utilization: Double
        let resetsAt: String

        enum CodingKeys: String, CodingKey {
            case utilization
            case resetsAt = "resets_at"
        }
    }
}
