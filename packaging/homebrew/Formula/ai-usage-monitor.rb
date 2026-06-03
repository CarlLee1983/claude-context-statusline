class AiUsageMonitor < Formula
  desc "Native macOS menu-bar monitor for Claude/Codex/Antigravity usage"
  homepage "https://github.com/CarlLee1983/claude-context-statusline"
  url "https://github.com/CarlLee1983/claude-context-statusline/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  depends_on xcode: ["16.0", :build]
  depends_on :macos

  def install
    cd "macos/AIUsageMonitor" do
      ENV["CONFIGURATION"] = "release"
      ENV["APP_VERSION"] = version.to_s
      system "./Scripts/build-app.sh"
      prefix.install ".build/AIUsageMonitor.app"
    end

    # 啟動器：本機編譯的 .app 不帶 quarantine，複製到使用者可寫的 ~/Applications
    # （路徑跨 brew upgrade 穩定，Launch-at-Login 的 SMAppService 才可靠）。
    (bin/"ai-usage-monitor").write <<~EOS
      #!/bin/bash
      set -euo pipefail
      SRC="#{opt_prefix}/AIUsageMonitor.app"
      DEST="$HOME/Applications/AIUsageMonitor.app"
      BIN="Contents/MacOS/AIUsageMonitor"
      mkdir -p "$HOME/Applications"
      if [ ! -d "$DEST" ] || [ "$SRC/$BIN" -nt "$DEST/$BIN" ]; then
        osascript -e 'tell application "AIUsageMonitor" to quit' 2>/dev/null || true
        pkill -x AIUsageMonitor 2>/dev/null || true
        rm -rf "$DEST"
        cp -R "$SRC" "$DEST"
      fi
      open "$DEST"
    EOS
    chmod 0755, bin/"ai-usage-monitor"
  end

  def caveats
    <<~EOS
      Launch the menu-bar app (first run installs it to ~/Applications):
        ai-usage-monitor
      Then click the menu-bar icon and enable "Launch at Login".
      After `brew upgrade`, run `ai-usage-monitor` again to refresh the copy.
    EOS
  end

  test do
    assert_predicate prefix/"AIUsageMonitor.app/Contents/MacOS/AIUsageMonitor", :executable?
  end
end
