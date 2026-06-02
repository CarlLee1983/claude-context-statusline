import Foundation

public enum CodexRateLimitParser {
    public static func parse(_ data: Data) throws -> ProviderSnapshot {
        let decoded = try JSONDecoder().decode(Response.self, from: data)
        guard let rateLimits = decoded.rateLimits else {
            return ProviderSnapshot(name: "Codex", shortName: "CX", windows: [], isAvailable: false)
        }

        var windows: [UsageWindow] = []
        if let primary = rateLimits.primary {
            windows.append(
                UsageWindow(
                    label: "5h",
                    percent: primary.usedPercent,
                    kind: .used,
                    resetAt: Date(timeIntervalSince1970: primary.resetsAt)
                )
            )
        }
        if let secondary = rateLimits.secondary {
            windows.append(
                UsageWindow(
                    label: "7d",
                    percent: secondary.usedPercent,
                    kind: .used,
                    resetAt: Date(timeIntervalSince1970: secondary.resetsAt)
                )
            )
        }

        return ProviderSnapshot(
            name: "Codex",
            shortName: "CX",
            plan: rateLimits.planType,
            windows: windows,
            isAvailable: !windows.isEmpty
        )
    }

    private struct Response: Decodable {
        let rateLimits: RateLimits?
    }

    private struct RateLimits: Decodable {
        let planType: String?
        let primary: Window?
        let secondary: Window?
    }

    private struct Window: Decodable {
        let usedPercent: Double
        let resetsAt: TimeInterval
    }
}
