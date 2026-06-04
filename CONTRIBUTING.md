# 貢獻指南 / Contributing

感謝你的貢獻！本專案刻意維持極簡，請在送出變更前留意以下原則。

Thanks for contributing! This project is deliberately minimal — please keep the
following principles in mind before submitting changes.

## 核心原則 / Core principles

本 repo 含兩個元件：`ctx-statusline.py`（Claude Code context 狀態列）、`macos/AIUsageMonitor`
（Swift 原生 App）。以下原則主要規範 Python 元件。
This repo has two components: `ctx-statusline.py` and the `macos/AIUsageMonitor` Swift app. The
principles below mainly govern the Python piece.

- **零相依 / Zero dependencies** — Python 元件只用標準庫；目標執行環境是 macOS 內建的
  `/usr/bin/python3`，不得引入硬相依。
  Python pieces use the standard library only; target runtime is macOS's built-in
  `/usr/bin/python3`, and must not introduce hard dependencies.
- **永不崩潰 / Never crash** — 狀態列／選單列指令絕不能拋出未捕捉的例外或噴錯。任何新邏輯都要
  有 fallback：ctx-statusline 退回「0% / 空進度條」。絕不印出 token。
  The statusline / menu-bar commands must never raise out or print errors. Every new path needs a
  fallback: ctx-statusline degrades to "0% / empty bar". Never print tokens.
- **小而專注 / Small & focused** — ctx-statusline 維持單檔；Swift App 把可測試邏輯放在
  `AIUsageMonitorCore`。

## 開發流程 / Workflow

1. 先寫測試，再改實作（TDD）。Write tests first, then implementation (TDD).
2. 執行測試 / Run tests:
   ```bash
   python3 -m unittest discover -s tests -v          # Python（ctx-statusline）
   cd macos/AIUsageMonitor && swift test             # Swift 原生 App / native app
   ```
3. Shell 腳本請通過 `bash -n` 與 `shellcheck`。
   Shell scripts must pass `bash -n` and `shellcheck`.
4. 文件改動請同步更新對應的 `README.md` 與 `README.en.md`（頂層、`macos/AIUsageMonitor/`
   各有一對）。
   Doc changes should update the matching `README.md` and `README.en.md` pair (top-level and
   `macos/AIUsageMonitor/` each have one).
5. 在 `CHANGELOG.md` 的 `Unreleased` 區塊記下變更。
   Note your change under the `Unreleased` section in `CHANGELOG.md`.

## Commit 訊息 / Commit messages

採用 Conventional Commits：`<type>: <subject>`（type 如 `feat` / `fix` / `docs` /
`refactor` / `test` / `chore`）。

Use Conventional Commits: `<type>: <subject>` (e.g. `feat` / `fix` / `docs` /
`refactor` / `test` / `chore`).
