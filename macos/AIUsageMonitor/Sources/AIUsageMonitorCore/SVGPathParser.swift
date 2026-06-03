import CoreGraphics
import Foundation

/// Minimal SVG path-data parser.
///
/// Supports the subset needed to render flat brand marks: move (`M`/`m`),
/// line (`L`/`l`), horizontal/vertical line (`H`/`h`, `V`/`v`), cubic Bézier
/// (`C`/`c`) and close (`Z`/`z`), including implicit command repetition and the
/// `m`→`l` / `M`→`L` promotion after the first move pair.
///
/// Coordinates are emitted in the path's own user-space units (no scaling and no
/// Y-flip); callers map them into a target rect. Kept pure so it is unit-testable
/// in `AIUsageMonitorCore`; the AppKit shell turns segments into an `NSBezierPath`.
public enum SVGPathParser {
    public enum Segment: Equatable {
        case move(CGPoint)
        case line(CGPoint)
        case curve(to: CGPoint, control1: CGPoint, control2: CGPoint)
        case close
    }

    private static let tokenPattern = try? NSRegularExpression(
        pattern: "[a-zA-Z]|-?\\d*\\.\\d+|-?\\d+"
    )

    public static func parse(_ path: String) -> [Segment] {
        let tokens = tokenize(path)
        guard !tokens.isEmpty else { return [] }

        var segments: [Segment] = []
        var current = CGPoint.zero      // current point
        var start = CGPoint.zero        // sub-path start (for close)
        var command: Character?
        var index = 0

        func nextNumber() -> CGFloat? {
            guard index < tokens.count, let value = Double(tokens[index]) else { return nil }
            index += 1
            return CGFloat(value)
        }

        while index < tokens.count {
            if let letter = tokens[index].first, letter.isLetter {
                command = letter
                index += 1
            }
            guard let cmd = command else { break }

            switch cmd {
            case "M", "m":
                guard let x = nextNumber(), let y = nextNumber() else { return segments }
                current = (cmd == "m") ? CGPoint(x: current.x + x, y: current.y + y) : CGPoint(x: x, y: y)
                start = current
                segments.append(.move(current))
                command = (cmd == "m") ? "l" : "L"   // subsequent pairs are line-to
            case "L", "l":
                guard let x = nextNumber(), let y = nextNumber() else { return segments }
                current = (cmd == "l") ? CGPoint(x: current.x + x, y: current.y + y) : CGPoint(x: x, y: y)
                segments.append(.line(current))
            case "H", "h":
                guard let x = nextNumber() else { return segments }
                current = (cmd == "h") ? CGPoint(x: current.x + x, y: current.y) : CGPoint(x: x, y: current.y)
                segments.append(.line(current))
            case "V", "v":
                guard let y = nextNumber() else { return segments }
                current = (cmd == "v") ? CGPoint(x: current.x, y: current.y + y) : CGPoint(x: current.x, y: y)
                segments.append(.line(current))
            case "C", "c":
                guard
                    let x1 = nextNumber(), let y1 = nextNumber(),
                    let x2 = nextNumber(), let y2 = nextNumber(),
                    let x3 = nextNumber(), let y3 = nextNumber()
                else { return segments }
                let relative = (cmd == "c")
                let base = relative ? current : .zero
                let control1 = CGPoint(x: base.x + x1, y: base.y + y1)
                let control2 = CGPoint(x: base.x + x2, y: base.y + y2)
                let end = CGPoint(x: base.x + x3, y: base.y + y3)
                segments.append(.curve(to: end, control1: control1, control2: control2))
                current = end
            case "Z", "z":
                segments.append(.close)
                current = start
            default:
                // Unsupported command (e.g. arcs); stop rather than misread coordinates.
                return segments
            }
        }
        return segments
    }

    private static func tokenize(_ path: String) -> [String] {
        guard let regex = tokenPattern else { return [] }
        let range = NSRange(path.startIndex..., in: path)
        return regex.matches(in: path, range: range).compactMap { match in
            Range(match.range, in: path).map { String(path[$0]) }
        }
    }
}
