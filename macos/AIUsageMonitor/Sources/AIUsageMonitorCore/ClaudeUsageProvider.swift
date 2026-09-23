import Foundation

/// Reads Claude subscription usage through the OAuth endpoint, then falls back
/// to Claude Code's local `/usage` command when the endpoint is unavailable.
/// The access token is only held in memory and never logged or rendered.
public struct ClaudeUsageProvider: ProviderSnapshotProviding {
    private let readAccessToken: @Sendable () -> String?
    private let fetchUsage: @Sendable (String) async -> Data?
    private let captureCLIUsage: @Sendable () -> Data?
    private let now: @Sendable () -> Date

    public init() {
        self.init(
            readAccessToken: { Self.readKeychainAccessToken() },
            fetchUsage: { await Self.fetchAPIUsage(token: $0) },
            captureCLIUsage: { ClaudeCLIUsageCapture.capture() },
            now: { .now }
        )
    }

    init(
        readAccessToken: @escaping @Sendable () -> String?,
        fetchUsage: @escaping @Sendable (String) async -> Data?,
        captureCLIUsage: @escaping @Sendable () -> Data?,
        now: @escaping @Sendable () -> Date
    ) {
        self.readAccessToken = readAccessToken
        self.fetchUsage = fetchUsage
        self.captureCLIUsage = captureCLIUsage
        self.now = now
    }

    public func snapshot() async -> ProviderSnapshot {
        let unavailable = ProviderSnapshot(
            providerID: .claudeCode, name: "Claude Code", shortName: "CC", windows: [], isAvailable: false
        )
        if let token = readAccessToken(), let data = await fetchUsage(token) {
            let windows = ClaudeUsageParser.parse(data)
            if !windows.isEmpty {
                return ProviderSnapshot(
                    providerID: .claudeCode, name: "Claude Code", shortName: "CC", windows: windows
                )
            }
        }

        // Subprocess capture blocks for a few seconds; keep it off the
        // cooperative executor so other providers can refresh concurrently.
        let capture = captureCLIUsage
        guard let data = await Task.detached(priority: .utility, operation: { capture() }).value else {
            return unavailable
        }
        let windows = ClaudeCLIUsageParser.parse(data, now: now())
        guard !windows.isEmpty else { return unavailable }
        return ProviderSnapshot(providerID: .claudeCode, name: "Claude Code", shortName: "CC", windows: windows)
    }

    private static func readKeychainAccessToken() -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        process.arguments = ["find-generic-password", "-s", "Claude Code-credentials", "-w"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return nil }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let oauth = object["claudeAiOauth"] as? [String: Any],
            let token = oauth["accessToken"] as? String
        else { return nil }
        return token
    }

    private static func fetchAPIUsage(token: String) async -> Data? {
        guard let url = URL(string: "https://api.anthropic.com/api/oauth/usage") else { return nil }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("oauth-2025-04-20", forHTTPHeaderField: "anthropic-beta")
        request.timeoutInterval = 8
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard
                let http = response as? HTTPURLResponse,
                (200..<300).contains(http.statusCode)
            else { return nil }
            return data
        } catch {
            return nil
        }
    }
}
