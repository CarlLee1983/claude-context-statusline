import Darwin
import Foundation

/// Drives the Antigravity CLI's `/usage` slash command and returns the raw panel
/// text, or nil on any failure. Mirrors the reference SwiftBar
/// `_capture_antigravity_usage_text`.
///
/// The slash command only renders inside a TTY, so a plain pipe won't do — the CLI
/// is run against a pseudo-terminal. This is a thin I/O boundary (not unit tested);
/// the parsing it feeds (`AntigravityUsageParser`) is tested separately. It must
/// never crash: every path degrades to nil.
public enum AntigravityUsageTextCapture {
    public static func capture(timeout: TimeInterval = 12) -> String? {
        guard let agy = resolveAgy() else { return nil }

        // Open a pseudo-terminal pair.
        let master = posix_openpt(O_RDWR)
        guard master >= 0 else { return nil }
        guard grantpt(master) == 0, unlockpt(master) == 0,
              let slaveNamePtr = ptsname(master) else {
            close(master)
            return nil
        }
        let slave = open(String(cString: slaveNamePtr), O_RDWR)
        guard slave >= 0 else {
            close(master)
            return nil
        }

        // Enlarge the TTY so `/usage` renders the full model list, not just a
        // small viewport (matches the reference 80x120 window size).
        var size = winsize(ws_row: 80, ws_col: 120, ws_xpixel: 0, ws_ypixel: 0)
        _ = ioctl(slave, TIOCSWINSZ, &size)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: agy)
        let slaveHandle = FileHandle(fileDescriptor: slave, closeOnDealloc: false)
        process.standardInput = slaveHandle
        process.standardOutput = slaveHandle
        process.standardError = slaveHandle

        do {
            try process.run()
        } catch {
            close(slave)
            close(master)
            return nil
        }
        close(slave) // parent keeps only the master end

        defer {
            writeToMaster(master, "\u{1B}/quit\r")
            if process.isRunning { process.terminate() }
            // Escalate to SIGKILL if SIGTERM is ignored, so waitUntilExit() (and
            // therefore the whole refresh) can never hang on a stuck TUI.
            let pid = process.processIdentifier
            let killer = DispatchWorkItem { kill(pid, SIGKILL) }
            DispatchQueue.global().asyncAfter(deadline: .now() + 2, execute: killer)
            process.waitUntilExit()
            killer.cancel()
            close(master)
        }

        return drive(master: master, timeout: timeout)
    }

    /// Reads from the master, sends `/usage` once the prompt is ready, and stops
    /// shortly after the quota panel appears (or at the deadline).
    private static func drive(master: Int32, timeout: TimeInterval) -> String? {
        var chunks = ""
        var sent = false
        var sawUsage = false
        var deadline = Date().addingTimeInterval(timeout)
        var buffer = [UInt8](repeating: 0, count: 8192)

        while Date() < deadline {
            var pollFD = pollfd(fd: master, events: Int16(POLLIN), revents: 0)
            guard poll(&pollFD, 1, 200) > 0 else { continue }

            let count = read(master, &buffer, buffer.count)
            if count <= 0 { break }
            chunks += String(decoding: buffer[0..<count], as: UTF8.self)

            if !sent, chunks.contains("? for shortcuts") || chunks.contains("Google AI Pro") {
                writeToMaster(master, "/usage\r")
                sent = true
            }
            if chunks.contains("Model Quota") {
                sawUsage = true
                // Read a little longer so the TUI finishes painting the model rows.
                let soon = Date().addingTimeInterval(0.8)
                if soon < deadline { deadline = soon }
            }
        }

        return sawUsage ? chunks : nil
    }

    private static func writeToMaster(_ master: Int32, _ string: String) {
        let bytes = Array(string.utf8)
        _ = bytes.withUnsafeBytes { raw in
            write(master, raw.baseAddress, raw.count)
        }
    }

    /// Locate `agy`: the conventional install dir, common bin dirs, then the login
    /// shell. Kept narrow on purpose; the broader node-manager probing the SwiftBar
    /// plugin needs is for `codex`, not `agy`.
    private static func resolveAgy() -> String? {
        let fileManager = FileManager.default
        let candidates = [
            NSHomeDirectory() + "/.local/bin/agy",
            "/opt/homebrew/bin/agy",
            "/usr/local/bin/agy",
        ]
        for path in candidates where fileManager.isExecutableFile(atPath: path) {
            return path
        }
        return loginShellLookup()
    }

    private static func loginShellLookup() -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", "command -v agy"]
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
