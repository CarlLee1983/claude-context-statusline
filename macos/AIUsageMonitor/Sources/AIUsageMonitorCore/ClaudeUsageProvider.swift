import Foundation

/// Reads the Claude Code OAuth token from the macOS Keychain and queries the
/// Anthropic usage endpoint. All failures collapse to an unavailable snapshot.
/// The access token is only held in memory and never logged or rendered.
public struct ClaudeUsageProvider: Sendable {
    public init() {}

    public func snapshot() async -> ProviderSnapshot {
        let unavailable = ProviderSnapshot(
            name: "Claude Code", shortName: "CC", windows: [], isAvailable: false
        )
        guard let token = Self.readAccessToken() else { return unavailable }
        guard let data = await Self.fetchUsage(token: token) else { return unavailable }
        let windows = ClaudeUsageParser.parse(data)
        guard !windows.isEmpty else { return unavailable }
        return ProviderSnapshot(name: "Claude Code", shortName: "CC", windows: windows)
    }

    private static func readAccessToken() -> String? {
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

    private static func fetchUsage(token: String) async -> Data? {
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
