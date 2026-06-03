# 設計：AI CLI 完成提示（Ghostty 分頁標記）

- 日期：2026-06-03
- 狀態：待實作
- 範圍：在本 repo 新增第四個元件 `bell/`，讓 AI CLI 跑完一輪時，透過終端機 BEL 觸發 Ghostty 把分頁/視窗標記為「需要注意」。

## 1. 目標與動機

使用者在 **Ghostty 同一視窗、多個分頁** 裡分別跑 Claude Code、Codex 等 AI CLI，常切去別的 App 等它跑完。希望「對話完成」時 Ghostty 分頁上出現提示，**只要視覺標記，不要聲音、不要 macOS 橫幅**。

## 2. 核心架構：觸發層 + 顯示層

```
[CLI 跑完一輪] → 送出 BEL (\a) 到 /dev/tty → [Ghostty 收到 bell] → 標記分頁/視窗
   觸發層（各 CLI 各自掛，與終端機版本無關）        顯示層（Ghostty 設定）
```

**分層理由**：BEL 是終端機通用語言，所有 CLI 都能送、Ghostty 一定收得到。
「怎麼偵測完成」留在各 CLI（用它們各自的 hook/notify），「怎麼呈現」留給 Ghostty。
未來 Ghostty 1.4 修好分頁標記後，**觸發層完全不用改**，呈現自動變好。

### 已知環境限制（誠實記錄）

- 本機 Ghostty `1.3.1`（2026-06 最新穩定；1.4 預計 2026-09）。
- macOS 1.3.1 上 `bell-features = title` 有 regression：**背景分頁的 🔔 要等該分頁被點到才更新**，正好是「切走等它跑完」情境。
  來源：Ghostty Discussion #10692、1.3.1 Release Notes。
- 因此 v1 同時開 `attention`（未聚焦時跳 Dock，**可靠保底**）與 `title`（分頁 🔔，回到視窗時可靠，1.4 後即時）。
- 前提：CLI 預設**不會**自動送 BEL，必須由本元件掛上。

## 3. 元件結構

新增 `bell/`，與 `swiftbar/` 平行：

```
bell/
  notify.sh        # BEL 發送器（來源感知；永不讓 host CLI 崩潰）
  install.sh       # 合併三邊設定（備份、只增不刪、可重複執行）
  uninstall.sh     # 移除本元件加入的設定，還原
  README.md        # 繁中（主）
  README.en.md     # 英文（同步）
tests/
  test_bell.py     # 純標準庫 unittest，依路徑載入
```

頂層 README（繁中＋英文）新增第四元件概覽；`CHANGELOG.md` 記錄。

## 4. 觸發層：`bell/notify.sh`

單一腳本，依「來源」決定是否送 BEL，**絕不 exit 非 0、絕不污染 host CLI**：

```sh
#!/bin/sh
# 用法：notify.sh <source> [payload]
#   claude  → 無條件送 BEL（Stop hook 已代表完成）
#   codex   → 解析 payload JSON，僅在 type=agent-turn-complete 時送
src="$1"
case "$src" in
  codex)
    # payload 是 Codex 傳入的 JSON 字串（$2）
    case "$2" in
      *'"type":"agent-turn-complete"'*|*'"type": "agent-turn-complete"'*) : ;;
      *) exit 0 ;;
    esac
    ;;
esac
printf '\a' > /dev/tty 2>/dev/null || true
exit 0
```

設計要點：
- **永不崩潰**：寫 `/dev/tty` 失敗（無控制終端機、被 redirect）一律吞掉，`exit 0`。對齊 repo 既有「狀態列/外掛永不崩潰」鐵則。
- **來源感知**：Claude 的 Stop hook 不帶完成型別，無條件響；Codex 的 notify 對所有事件呼叫，需自行過濾 `agent-turn-complete`。
- 純 `/bin/sh`，零相依。

## 5. 顯示層：Ghostty 設定

目標檔：`~/.config/ghostty/config`（XDG 主設定）。加入：

```
bell-features = title,attention
```

- 明確只列這兩項 ⇒ **靜音、純視覺**（不繼承預設可能含的 audio/system）。
- **雙位置歧義**：本機另有 `~/Library/Application Support/com.mitchellh.ghostty/config`。
  安裝器鎖定 XDG 那份；若 app-support 那份也定義了 `bell-features`，**只警告、不動它**，並提示使用者兩份的關係。
- 已存在 `bell-features` 行：**不覆蓋**，印出目前值與建議值供使用者自行決定。
- 套用需重載設定（Ghostty `Cmd+Shift+,`）或重開——README 註明。

## 6. 安裝層：`bell/install.sh` / `uninstall.sh`

共同鐵則（沿用 repo 既有策略）：
- 改動前一律備份成 `<file>.bak.<timestamp>`。
- **只增不刪既有設定**；偵測已安裝則不重複加（冪等）。
- 任一邊失敗不影響其他邊；最後印出總結（成功/略過/需手動）。
- 支援 `CLAUDE_CONFIG_DIR` 覆寫 Claude 設定目錄（測試用）。

### 6.1 Claude Code（`settings.json`，JSON）

沿用 repo 現成的 `/usr/bin/python3` heredoc 合併：在 `hooks.Stop` 陣列加入一個 matcher 物件，`command` 指向 `bell/notify.sh claude` 的絕對路徑。

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "/abs/path/bell/notify.sh claude" } ] }
    ]
  }
}
```

- 合併時保留既有 `hooks` 與其他 key；以 command 路徑比對避免重複加。
- settings.json 非合法 JSON 則中止不動（同既有 install.sh 行為）。

### 6.2 Codex（`config.toml`，TOML）— 守衛式自動 append

**限制**：`/usr/bin/python3` 是 3.9.6，**無 `tomllib`**（連讀都不能用 stdlib TOML）。
因此用**純文字行掃描**判斷，不解析整份 TOML：

1. 備份 `config.toml`（保留 `0600` 權限）。
2. 掃描是否已有頂層 `notify`（行首符合 `^[ \t]*notify[ \t]*=`，且出現在第一個 `^[ \t]*\[` 表頭之前）。
   - **已有** → 不動，印出手動提示（請使用者自行把 notify 指向 `bell/notify.sh codex`）。
   - **沒有** → 在檔案**最前面**（任何 `[table]` 之前）append 一段帶註解的：
     ```toml
     # added by claude-context-statusline bell/install.sh
     notify = ["/abs/path/bell/notify.sh", "codex"]
     ```
   - Codex 會以 `notify.sh codex <json>` 呼叫；腳本自行過濾 `agent-turn-complete`。
3. 改寫後 `chmod 600`。

### 6.3 Ghostty（行導向純文字）

如 §5：偵測 → 無則 append `bell-features = title,attention`；有則警告不覆蓋；處理雙位置。

### uninstall.sh

逐邊移除本元件加入的內容（以註解標記或 command 路徑辨識），備份後還原；找不到就略過。

## 7. 測試（`tests/test_bell.py`，純標準庫）

依路徑用 `importlib`/`subprocess` 載入並驗證**純邏輯**：

1. `notify.sh` 來源過濾：
   - `claude` → 一定嘗試送（用可寫的假 tty/重導驗證有輸出 `\a`，或驗證 exit 0）。
   - `codex` + payload 含 `agent-turn-complete` → 送；payload 為其他型別 → 不送。
   - 無 `/dev/tty` 可寫時 → 仍 `exit 0`，不報錯。
2. Claude settings 合併（把 heredoc 合併邏輯抽成可呼叫的小段或在 `CLAUDE_CONFIG_DIR` 暫存目錄跑 install）：
   - 空檔/既有 hooks 並存/重複執行冪等/壞 JSON 中止。
3. Codex 行掃描：已有頂層 `notify` → 不動；無 → append 在第一個 table 前；權限維持 600。

> 注：`/dev/tty` 與真實終端機互動的部分屬 thin boundary，比照 repo 慣例（如 Antigravity PTY）**不強求單測**，邏輯/解析才測。

## 8. 範圍與後續（YAGNI）

**v1 納入**：Claude Code（Stop）、Codex（notify）、Ghostty 顯示設定、雙語文件、測試。

**列為後續、先調查**：
- **Antigravity**：完成事件/hook 機制未確認，v1 不做；README 標「尚未支援」，spec 留待調查其有無 notify/hook。
- 之後若要：聲音、macOS 橫幅、OSC 9 桌面通知——皆只需改 `notify.sh` 一處（分層設計的好處），不在 v1。

## 9. 驗收標準

1. 跑 `bell/install.sh` 後：三邊設定各有備份；Claude `settings.json` 出現 Stop hook；Codex（無既有 notify 時）出現 notify 指向腳本；Ghostty XDG config 出現 `bell-features = title,attention`。
2. 在 Ghostty 一個背景分頁跑 Claude，一輪回完後切回視窗：該分頁標題出現 🔔（前景可靠）；切到別的 App 時跑完：Dock 跳注意。
3. 重複跑 `install.sh` 不會重複加任何一行。
4. `bell/uninstall.sh` 還原三邊，留備份。
5. `python3 -m unittest discover -s tests -v` 全綠。
6. 任一 CLI 在被 redirect / 無 tty 情境呼叫 `notify.sh` 都不報錯、不中斷 host。
