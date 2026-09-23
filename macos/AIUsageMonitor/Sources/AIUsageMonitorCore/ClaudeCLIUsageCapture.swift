import Darwin
import Foundation

/// Runs Claude Code's local `/usage` command with restricted tools/settings,
/// no MCP servers, and no session persistence. Captured output stays in memory.
enum ClaudeCLIUsageCapture {
    static func capture(timeout: TimeInterval = 15) -> Data? {
        guard let executable = resolveExecutable() else { return nil }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = [
            "--print", "/usage", "--output-format", "json",
            "--no-session-persistence", "--restricted", "--strict-mcp-config",
            "--tools", "", "--max-budget-usd", "0.001",
        ]
        process.currentDirectoryURL = URL(fileURLWithPath: "/tmp", isDirectory: true)
        process.standardInput = FileHandle.nullDevice
        let stdout = Pipe()
        process.standardOutput = stdout
        process.standardError = FileHandle.nullDevice

        let home = NSHomeDirectory()
        let binDir = (executable as NSString).deletingLastPathComponent
        var environment = [
            "HOME": home,
            "USER": NSUserName(),
            "PATH": [binDir, home + "/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
                .joined(separator: ":"),
            "TMPDIR": FileManager.default.temporaryDirectory.path,
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
        ]
        // Claude Code keys the credential store to this directory when set.
        if let config = ProcessInfo.processInfo.environment["CLAUDE_CONFIG_DIR"], !config.isEmpty {
            environment["CLAUDE_CONFIG_DIR"] = config
        }
        process.environment = environment

        do { try process.run() } catch { return nil }

        defer {
            if process.isRunning { process.terminate() }
            let pid = process.processIdentifier
            let killer = DispatchWorkItem { if process.isRunning { kill(pid, SIGKILL) } }
            DispatchQueue.global().asyncAfter(deadline: .now() + 2, execute: killer)
            process.waitUntilExit()
            killer.cancel()
        }

        // A child can keep stdout open after the CLI exits, so read with poll
        // rather than readDataToEndOfFile. Bound output as well as wall time.
        let fd = stdout.fileHandleForReading.fileDescriptor
        let flags = fcntl(fd, F_GETFL)
        guard flags >= 0, fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0 else { return nil }
        var output = Data()
        var buffer = [UInt8](repeating: 0, count: 4_096)
        let deadline = Date().addingTimeInterval(timeout)
        var reachedEOF = false
        while Date() < deadline {
            var pollFD = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
            let ready = poll(&pollFD, 1, 100)
            if ready < 0 { return nil }
            if ready == 0 { continue }
            let count = read(fd, &buffer, buffer.count)
            if count == 0 {
                reachedEOF = true
                break
            }
            if count < 0 {
                if errno == EAGAIN || errno == EINTR { continue }
                return nil
            }
            output.append(contentsOf: buffer[..<count])
            if output.count > 64 * 1_024 { return nil }
        }
        guard reachedEOF else { return nil }
        while process.isRunning && Date() < deadline { usleep(50_000) }
        guard !process.isRunning, process.terminationStatus == 0 else { return nil }
        return output
    }

    private static func resolveExecutable() -> String? {
        let home = NSHomeDirectory()
        let candidates = [
            home + "/.local/bin/claude",
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
        ] + (ProcessInfo.processInfo.environment["PATH"] ?? "")
            .split(separator: ":")
            .map { String($0) + "/claude" }
        return candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) })
    }
}
