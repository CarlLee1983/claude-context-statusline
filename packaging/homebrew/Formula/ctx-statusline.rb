class CtxStatusline < Formula
  desc "Claude Code statusline showing context-window usage"
  homepage "https://github.com/CarlLee1983/claude-context-statusline"
  url "https://github.com/CarlLee1983/claude-context-statusline/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  def install
    bin.install "ctx-statusline.py" => "ctx-statusline"
    bin.install "ctx-statusline-setup"
  end

  def caveats
    <<~EOS
      Wire the statusline into Claude Code, then restart a Claude Code session:
        ctx-statusline-setup
      Remove it later with:
        ctx-statusline-setup --remove
      Honors CLAUDE_CONFIG_DIR if your config lives outside ~/.claude.
    EOS
  end

  test do
    json = '{"model":{"id":"claude-opus-4-8","display_name":"Opus 4.8"},' \
           '"transcript_path":"/nonexistent.jsonl"}'
    output = pipe_output("/usr/bin/python3 #{bin}/ctx-statusline", json)
    assert_match "Opus", output
  end
end
