import Foundation

/// Parses the Anthropic OAuth usage endpoint payload into `.used` usage windows.
/// Pure and total: any malformed or missing data yields an empty array.
public enum ClaudeUsageParser {
    // ISO8601DateFormatter's date(from:) is thread-safe for reads; sharing one
    // instance avoids per-call allocation.
    private nonisolated(unsafe) static let iso8601 = ISO8601DateFormatter()

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
            resetAt: Self.iso8601.date(from: node.resetsAt)
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
