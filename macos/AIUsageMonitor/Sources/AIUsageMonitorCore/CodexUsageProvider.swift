import Foundation

/// Drives `codex app-server` over JSON-RPC to read account rate limits, then
/// feeds the `result` payload to `CodexRateLimitParser`. A watchdog guarantees
/// the subprocess is terminated so this never hangs. Failures collapse to an
/// unavailable snapshot.
public struct CodexUsageProvider: ProviderSnapshotProviding {
    public init() {}

    public func snapshot() async -> ProviderSnapshot {
        let unavailable = ProviderSnapshot(
            name: "Codex", shortName: "CX", windows: [], isAvailable: false
        )
        guard let result = Self.readRateLimitsResult() else { return unavailable }
        return (try? CodexRateLimitParser.parse(result)) ?? unavailable
    }

    /// Returns the JSON-encoded `result` object (containing `rateLimits`) or nil.
    private static func readRateLimitsResult() -> Data? {
        guard let codex = CodexExecutableResolver.resolve() else { return nil }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: codex)
        process.arguments = ["app-server"]
        var environment = ProcessInfo.processInfo.environment
        let binDir = (codex as NSString).deletingLastPathComponent
        environment["PATH"] = binDir + ":" + (environment["PATH"] ?? "")
        process.environment = environment

        let inPipe = Pipe()
        let outPipe = Pipe()
        process.standardInput = inPipe
        process.standardOutput = outPipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return nil }

        // Deterministically reap the child on every exit path (no lazy zombie).
        defer {
            if process.isRunning { process.terminate() }
            process.waitUntilExit()
        }

        // Watchdog: guarantee termination so availableData reaches EOF.
        let watchdog = DispatchWorkItem { if process.isRunning { process.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + 8, execute: watchdog)

        func send(_ object: [String: Any]) {
            guard let data = try? JSONSerialization.data(withJSONObject: object) else { return }
            // Use the throwing API: write(_:) raises an uncatchable ObjC exception
            // on a broken pipe, which would violate the never-crash invariant.
            try? inPipe.fileHandleForWriting.write(contentsOf: data)
            try? inPipe.fileHandleForWriting.write(contentsOf: Data("\n".utf8))
        }

        send([
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": ["clientInfo": [
                "name": "ai-usage-monitor", "title": "AI Usage Monitor", "version": "0.1",
            ]],
        ])
        send(["jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": [:]])
        // Do NOT close stdin here: codex app-server treats stdin EOF as a
        // shutdown signal and exits before emitting the rateLimits result.
        // The read loop breaks on the id==2 result; the watchdog handles hangs.

        let handle = outPipe.fileHandleForReading
        var buffer = Data()
        var result: Data?
        while true {
            let chunk = handle.availableData
            if chunk.isEmpty { break } // EOF (process exited or watchdog fired)
            buffer.append(chunk)
            while let newline = buffer.firstIndex(of: 0x0A) {
                let lineData = buffer.subdata(in: buffer.startIndex..<newline)
                buffer.removeSubrange(buffer.startIndex...newline)
                guard
                    let message = try? JSONSerialization.jsonObject(with: lineData) as? [String: Any],
                    (message["id"] as? Int) == 2,
                    let resultObject = message["result"]
                else { continue }
                result = try? JSONSerialization.data(withJSONObject: resultObject)
            }
            if result != nil { break }
        }

        watchdog.cancel()
        return result
    }
}
