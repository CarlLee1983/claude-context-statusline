import Foundation

/// Parses the local opencode Antigravity accounts file
/// (`~/.config/opencode/antigravity-accounts.json`).
///
/// Antigravity has no public percentage-usage endpoint to reuse, so this is the
/// conservative fallback when `agy /usage` can't be captured: an account existing
/// means "ready"; an unexpired rate-limit reset means that quota pool is fully
/// limited (0% remaining) until it resets. Mirrors the reference SwiftBar
/// `provider_antigravity` accounts path.
public enum AntigravityAccountsParser {
    public struct Result: Equatable, Sendable {
        public let plan: String?
        public let windows: [UsageWindow]
        /// True when the file held at least one account (i.e. Antigravity is
        /// configured locally) — distinguishes "ready/limited" from "unavailable".
        public let hasAccounts: Bool
    }

    public static func parse(_ data: Data, now: Date = .now) -> Result {
        let unavailable = Result(plan: nil, windows: [], hasAccounts: false)

        guard
            let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let accounts = root["accounts"] as? [[String: Any]],
            !accounts.isEmpty
        else { return unavailable }

        let plan = "\(accounts.count) acct\(accounts.count == 1 ? "" : "s")"
        let nowMs = now.timeIntervalSince1970 * 1000

        // Same quota pool across multiple accounts -> keep the latest reset. Only
        // Antigravity's own pools (Claude / Gemini) are surfaced; plain Gemini CLI
        // quota (`gemini-cli`) is deliberately excluded to avoid name confusion.
        var pools: [String: Double] = [:]
        for account in accounts {
            guard let resets = account["rateLimitResetTimes"] as? [String: Any] else { continue }
            for (key, rawValue) in resets {
                guard let value = numeric(rawValue), value > nowMs else { continue }
                if key == "claude" || key.hasPrefix("claude:") {
                    pools["Claude"] = max(pools["Claude"] ?? 0, value)
                } else if key == "gemini-antigravity" || key.hasPrefix("gemini-antigravity:") {
                    pools["Gemini"] = max(pools["Gemini"] ?? 0, value)
                }
            }
        }

        let windows: [UsageWindow] = ["Claude", "Gemini"].compactMap { label in
            guard let resetMs = pools[label] else { return nil }
            return UsageWindow(
                label: label,
                percent: 100,
                kind: .used,
                resetAt: Date(timeIntervalSince1970: resetMs / 1000)
            )
        }

        return Result(plan: plan, windows: windows, hasAccounts: true)
    }

    private static func numeric(_ value: Any) -> Double? {
        if let number = value as? NSNumber, !(value is Bool) { return number.doubleValue }
        return nil
    }
}
