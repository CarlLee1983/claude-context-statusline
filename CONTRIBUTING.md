# 貢獻指南 / Contributing

感謝你的貢獻！本專案刻意維持極簡，請在送出變更前留意以下原則。

Thanks for contributing! This project is deliberately minimal — please keep the
following principles in mind before submitting changes.

## 核心原則 / Core principles

- **零相依 / Zero dependencies** — 只用 Python 標準庫；目標執行環境是 macOS 內建的
  `/usr/bin/python3`。請勿引入第三方套件。
  Standard library only; the target runtime is macOS's built-in `/usr/bin/python3`.
  Do not add third-party packages.
- **永不崩潰 / Never crash** — 狀態列指令絕不能拋出未捕捉的例外或噴錯。任何新邏輯都要
  有 fallback，最終都退回「0% / 空進度條」。
  The statusline command must never raise out or print errors. Every new path needs
  a fallback that degrades to the "0% / empty bar" display.
- **單檔、小而專注 / Single file, small & focused** — 核心邏輯維持在 `ctx-statusline.py`。

## 開發流程 / Workflow

1. 先寫測試，再改實作（TDD）。Write tests first, then implementation (TDD).
2. 執行測試 / Run tests:
   ```bash
   python3 -m unittest discover -s tests -v
   ```
3. Shell 腳本請通過 `bash -n` 與 `shellcheck`。
   Shell scripts must pass `bash -n` and `shellcheck`.
4. 文件改動請同步更新 `README.md` 與 `README.en.md` 兩個語言版本。
   Doc changes should update both `README.md` and `README.en.md`.
5. 在 `CHANGELOG.md` 的 `Unreleased` 區塊記下變更。
   Note your change under the `Unreleased` section in `CHANGELOG.md`.

## Commit 訊息 / Commit messages

採用 Conventional Commits：`<type>: <subject>`（type 如 `feat` / `fix` / `docs` /
`refactor` / `test` / `chore`）。

Use Conventional Commits: `<type>: <subject>` (e.g. `feat` / `fix` / `docs` /
`refactor` / `test` / `chore`).
