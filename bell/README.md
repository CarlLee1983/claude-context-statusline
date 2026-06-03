# 完成提示 — bell/

**繁體中文** · [English](README.en.md)

AI CLI 跑完一輪時，透過終端機 BEL（`\a`）觸發 [Ghostty](https://ghostty.org/) 把分頁或視窗標記為「需要注意」。
切去別的 App 等 AI 回答時，Ghostty Dock 圖示跳動提示你；回到視窗後分頁標題也出現 🔔。

> **與其他元件的差別**：`ctx-statusline` 看的是「目前 session 把 context window 用了多少」；
> 原生 App 與 SwiftBar 外掛看的是「訂閱方案的 5h/7d 速率限制還剩多少」；
> 本元件（bell）看的是「完成事件 → 終端機分頁標記」，屬於**通知觸發**，不讀任何用量數字。

## 架構

```
[AI CLI 跑完一輪]
       │  Stop hook / notify
       ▼
  bell/notify.sh  ──── printf '\a' ──→  /dev/tty  ──→  [Ghostty 收到 BEL]
  （觸發層）                                              （顯示層）
                                                    標記分頁 🔔 / Dock 跳動
```

**兩層分離**的好處：觸發層（各 CLI 的 hook/notify）與顯示層（Ghostty 設定）互不耦合。
未來 Ghostty 版本修好即時分頁標記後，觸發層**完全不用改**，顯示自動變好。

## 需求

- macOS，系統內建 `/usr/bin/python3`（免額外安裝）
- [Ghostty](https://ghostty.org/)
- 各 CLI 視你實際使用而定：Claude Code、Codex

## 安裝

```bash
./bell/install.sh
```

安裝腳本會做三件事（皆先備份、只增不刪、可重複執行）：

1. **Claude Code** `~/.claude/settings.json` — 在 `hooks.Stop` 加入 `bell/notify.sh claude`
2. **Codex** `~/.codex/config.toml` — 在頂層加 `notify = ["/path/to/claude-context-statusline/bell/notify.sh", "codex"]`
   （安裝器會解析並寫入 `notify.sh` 的**絕對路徑**，不論之後從哪個 CWD 執行都仍有效；
   已有 `notify` 設定時，略過並提示手動指向本腳本）
3. **Ghostty** `~/.config/ghostty/config`（XDG 位置）— 加入 `bell-features = title,attention`
   （已有 `bell-features` 時，略過並印出目前值；若 `~/Library/Application Support/com.mitchellh.ghostty/config` 也有此設定，**只警告、不動它**）

完成後：
- **重新開啟 Claude Code session** 讓 Stop hook 生效
- **重新載入 Ghostty 設定**：`Cmd+Shift+,` 或重開 Ghostty

覆寫設定目錄（測試/非標準路徑）：

```bash
CLAUDE_CONFIG_DIR=/path/to/claude ./bell/install.sh
CODEX_HOME=/path/to/codex ./bell/install.sh
XDG_CONFIG_HOME=/path/to/xdg ./bell/install.sh
```

## 移除

```bash
./bell/uninstall.sh
```

逐邊移除本元件加入的內容（以標記識別），備份後還原；找不到就略過。

## Ghostty 設定說明

安裝後 Ghostty config 會出現：

```
bell-features = title,attention
```

- `title` — 分頁標題出現 🔔
- `attention` — 未聚焦時 Dock 圖示跳動（**可靠保底**）
- 明確只列這兩項 → **靜音、純視覺**（不繼承預設可能含的 audio/system）

**已知限制（Ghostty 1.3.1，2026-06）**：macOS 上的 `title` 有 regression——
背景分頁的 🔔 要等點到該分頁才更新，正好是「切走等它跑完」這個情境。
因此 `attention`（Dock 跳動）是目前最可靠的提示方式。
Ghostty 1.4（預計 2026-09）修正此 regression 後，分頁 🔔 即時性即自動改善，**不需更改本設定**。

## 各 CLI 觸發點

| CLI | 機制 | 備註 |
|-----|------|------|
| **Claude Code** | `hooks.Stop` — 每輪回完即觸發 | 無條件送 BEL |
| **Codex** | `config.toml` 的 `notify` — 過濾 `agent-turn-complete` | 已有 notify 設定時需手動整合 |
| **Antigravity** | **尚未支援** | 待調查其有無完成事件/hook 機制 |

## 永不崩潰原則

`notify.sh` 遵循 repo 既有的「永不讓 host CLI 崩潰」鐵則：

- 寫 `/dev/tty` 失敗（無控制終端機、被 redirect）一律吞掉，`exit 0`
- 純 `/bin/sh`，零相依，不會因環境差異而報錯
- `BELL_TTY` 可覆寫輸出目標（測試用）：`BELL_TTY=/tmp/fake-tty ./bell/notify.sh claude`

## 測試

```bash
python3 -m unittest tests.test_bell -v
```

或一次跑全部測試：

```bash
python3 -m unittest discover -s tests -v
```

測試涵蓋：`notify.sh` 來源過濾、Claude settings 合併（空檔/既有/冪等/壞 JSON）、
Codex 行掃描（已有 notify/無 notify/append 位置/權限）、Ghostty 設定合併。
