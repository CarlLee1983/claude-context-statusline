import Foundation

/// Locates the `codex` executable across PATH, common install dirs, and
/// versioned node-manager directories. The version-selection step is pure and
/// unit tested; the filesystem probing is a thin boundary.
public enum CodexExecutableResolver {
    /// Pure: pick the newest versioned candidate (lexicographic sort, last wins).
    /// Mirrors the reference Python `sorted(hits)[-1]` behaviour.
    static func selectNewest(from candidates: [String]) -> String? {
        candidates.sorted().last
    }

    /// Resolve the absolute path to `codex`, or nil if not found.
    public static func resolve() -> String? {
        let fileManager = FileManager.default
        let home = NSHomeDirectory()

        for dir in ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"] {
            let path = dir + "/codex"
            if fileManager.isExecutableFile(atPath: path) { return path }
        }

        let globRoots = [
            home + "/.nvm/versions/node",
            home + "/Library/Application Support/Herd/config/nvm/versions/node",
        ]
        var hits: [String] = []
        for root in globRoots {
            guard let entries = try? fileManager.contentsOfDirectory(atPath: root) else { continue }
            for entry in entries {
                let path = root + "/" + entry + "/bin/codex"
                if fileManager.isExecutableFile(atPath: path) { hits.append(path) }
            }
        }
        for fixed in [home + "/.volta/bin/codex", home + "/.local/bin/codex"] {
            if fileManager.isExecutableFile(atPath: fixed) { hits.append(fixed) }
        }
        if let newest = selectNewest(from: hits) { return newest }

        return loginShellLookup()
    }

    private static func loginShellLookup() -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", "command -v codex"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return nil }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let path = String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        return path.isEmpty ? nil : path
    }
}
