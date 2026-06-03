import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Codex executable resolver")
struct CodexExecutableResolverTests {
    @Test("selects the newest versioned path by sort order")
    func newest() {
        let candidates = [
            "/Users/x/.nvm/versions/node/v18.20.0/bin/codex",
            "/Users/x/.nvm/versions/node/v20.10.0/bin/codex",
            "/Users/x/.nvm/versions/node/v18.9.0/bin/codex",
        ]
        #expect(
            CodexExecutableResolver.selectNewest(from: candidates)
                == "/Users/x/.nvm/versions/node/v20.10.0/bin/codex"
        )
    }

    @Test("returns nil when there are no candidates")
    func none() {
        #expect(CodexExecutableResolver.selectNewest(from: []) == nil)
    }
}
