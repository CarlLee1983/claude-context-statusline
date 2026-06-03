# Homebrew tap 維護

本資料夾的 `Formula/*.rb` 是三個 formula 的**權威範本**。實際被使用者 tap 的是獨立 repo
`CarlLee1983/homebrew-tap`；`Scripts/release.sh` 在發版時把範本填入版本與 sha256 後推到該 repo。

## 一次性建立 tap repo

```bash
gh repo create CarlLee1983/homebrew-tap --public \
  --description "Homebrew tap for claude-context-statusline tools"
git clone https://github.com/CarlLee1983/homebrew-tap ../homebrew-tap
mkdir -p ../homebrew-tap/Formula
# 首次可手動複製範本並填入第一個版本的 sha256，或直接跑 release.sh
```

## 發版

```bash
# 1) 更新 CHANGELOG 的 Unreleased → 版本號
# 2) 跑發版腳本（會打 tag、算 sha、更新 tap 並推送）
Scripts/release.sh 0.2.0
```

`HOMEBREW_TAP_DIR` 可覆寫 tap 本地路徑（預設為與本專案同層的 `../homebrew-tap`）。

## 發版後驗證

```bash
brew untap CarlLee1983/tap 2>/dev/null || true
brew tap CarlLee1983/tap
brew install --build-from-source ctx-statusline ai-usage-monitor swiftbar-ai-usage
brew audit --strict --online CarlLee1983/tap/ctx-statusline
brew test CarlLee1983/tap/ctx-statusline
```
