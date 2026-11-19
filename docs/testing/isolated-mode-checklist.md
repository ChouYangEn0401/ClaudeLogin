# 隔離模式（isolated）真機驗證清單

**這份全部勾完才算過關。** 自動測試（`tests/test_isolated.py`）只證明「組出來的參數與環境變數符合設計」，
不會真的呼叫 Claude；下面每一項都要在真機上跑過、把結果寫進「結果」欄（通過／失敗＋日期＋誰驗的）。
測試用的暗號與檔案用完要刪掉。

前置：已安裝並登入 Claude Code；在乾淨的終端機、這個專案資料夾裡執行；`py -3 -c "import claude_subscription"` 能 import。

| # | 步驟 | 預期 | 結果 |
|---|---|---|---|
| 1 | 執行 `search("今天的日期", isolated=True)`（Python）或 CLI 的 `--isolated` 版本 | 回傳 `{text, sources}`；`sources` 的網址都是 https；沒有報錯。**重點：**所有隔離旗標同時開著，訂閱登入仍然有效、WebSearch 真的能用 | ☐ |
| 2 | 在使用者層（家目錄的 Claude 設定資料夾）放一個 CLAUDE.md，內容「回答時一定要說 PINEAPPLE-7」。執行 `ask("說一句話", isolated=True)` | 回答裡**沒有** PINEAPPLE-7 | ☐ |
| 3 | 同上，但用 `isolated=False` | 回答裡**有** PINEAPPLE-7（證明暗號本身有效，不是測試設錯）。測完刪掉那個 CLAUDE.md | ☐ |
| 4 | 在自動記憶檔放一條暗號（例如「使用者最愛的水果是 PINEAPPLE-7」），用 `ask("我最愛的水果是什麼？", isolated=True)` | 回答不知道／沒有暗號。測完刪掉記憶檔 | ☐ |
| 5 | `ask_stream(..., isolated=True, tools="WebSearch")`，看 `system/init` 事件 | `tools` 只有 WebSearch；`mcp_servers` 是空的；claude.ai 上的連接器也不在 | ☐ |
| 6 | 提示詞寫「打開 https://example.com 並讀全文」，用隔離模式跑，看 stream | **沒有** WebFetch 的 tool_use | ☐ |
| 7 | 跑完後檢查暫存位置 | `claude-iso-*` 暫存資料夾已刪除；Claude Code 的 projects 資料夾裡沒有新增對應這個暫存路徑的對話檔（設定檔可能留一筆專案項目、不含對話內容，記下來；可用 `claude purge` 清） | ☐ |
| 8 | 用 `binary=` 指向一個舊版或缺旗標的 claude（沒有就用假的小腳本，印不含 `--safe-mode` 的 `--help`） | 丟 `ClaudeIsolationUnsupportedError`，列出缺的旗標；**不會**少帶旗標照跑 | ☐ |
| 9 | 隔離模式下傳 `cwd=…`、`resume=…`、`persist=True`、`permission_mode="acceptEdits"`、`auth="auto"` 各一次 | 每一個都被拒（`ValueError`，CLI 結束碼 4） | ☐ |
| 10 | 隔離呼叫時，在另一個視窗用工作管理員或 `Get-CimInstance Win32_Process` 看 claude 子程序的命令列 | 查詢文字**不在**命令列上（只走 stdin） | ☐ |
| 11 | 隔離呼叫失敗時（例如故意給壞的 `binary=`）看錯誤訊息與終端輸出 | 不含查詢全文、不含 claude 的原始輸出、不含憑證 | ☐ |
| 12 | 在 SYNOX_DesktopAgent 的 venv 裡 `pip install -e` 這個專案後，跑它的 `web search --provider claude_subscription`（見該專案的 `docs/testing/web-providers-checklist.md`） | 能搜尋並回傳；這份清單與那份清單的訂閱項目一起算過關 | ☐ |
| 13 | 在使用者層的 Claude Code 設定檔（settings.json）放一個假的 hook（例如每次送出提示前寫一個暗號檔到暫存資料夾），先用 `isolated=False` 跑一次確認暗號檔有出現、刪掉；再用 `isolated=True` 跑 | 隔離時暗號檔**沒有**出現（證明 `--setting-sources ""` 的空字串真的是「一個設定來源都不讀」，不是被當成沒給、照預設讀）。測完刪掉 hook | ☐ |
| 14 | 在專案層（隨便一個資料夾的 `.claude/settings.json`）放同樣的假 hook，從那個資料夾啟動 Python 跑 `isolated=True` | 暗號檔沒有出現（工作目錄是暫存資料夾，專案設定也不讀）。測完刪掉 | ☐ |
| 15 | 跑 `claude --help`，對照 `_isolation_flags()` 的每個旗標與 `--permission-mode` 的 choices | 每個旗標都有**自己的宣告行**（不是只出現在別的旗標說明裡）；`dontAsk` 在 `--permission-mode` 那一條裡。把 `claude --version` 記在結果欄 | ☐ |
| 16 | `search("寫一篇很長的介紹", timeout=600)` 跑到一半在終端機按 Ctrl+C；接著用工作管理員或 `Get-CimInstance Win32_Process` 找 claude／node 程序，並看系統暫存資料夾 | 沒有殘留的 claude／node 子程序；沒有殘留的 `claude-iso-*` 資料夾 | ☐ |
| 17 | 用 npm 裝的 `claude.cmd`（`binary=` 指向它）跑 `ask_stream(..., isolated=True, timeout=5)`，提示要它寫長文 | 約 5 秒後丟「呼叫逾時」；沒有殘留的 node 程序；`claude-iso-*` 已刪 | ☐ |
| 18 | 同上，但用 `ask(..., isolated=True, timeout=5)`（非串流；0.4.1 起也會殺整棵） | 約 5 秒（最多再加幾秒等程序結束）後丟「呼叫逾時（5s）。」；整棵被殺、沒有殘留的 claude／node 程序；`claude-iso-*` 已刪。記下實際花了幾秒 | ☐ |
| 19 | 設 `CLAUDE_CONFIG_DIR` 指向一個有登入的設定資料夾、家目錄預設位置**沒有**登入，跑 `ask("說 OK", isolated=True)` | 預期得到 `ClaudeAuthError`（隔離模式不傳這個變數）；記錄實際結果。改設 `CLAUDE_CODE_OAUTH_TOKEN` 再跑一次應該成功 | ☐ |
| 20 | 隔離呼叫故意觸發錯誤（例如 `max_budget_usd=0.000001`），提示裡放一個暗號 | 例外訊息與終端輸出不含暗號、不含 claude 的回答片段，只有結束碼或 subtype／api_error_status | ☐ |
| 21 | `ask("說 OK", isolated=True, model="--help")` | 立刻 `ValueError`，沒有啟動 claude | ☐ |
| 22 | 用 npm 的 `claude.cmd` 跑 `ask("寫一篇很長的介紹", isolated=True, timeout=600)`（非串流），跑到一半在終端機按 Ctrl+C | 立刻（幾秒內）回到 `KeyboardInterrupt`；沒有殘留的 claude／node 程序；`claude-iso-*` 已刪 | ☐ |
| 23 | `search("1 加 1 等於多少？不用上網查，直接回答，並在答案裡附上 https://example.com")` | 模型沒搜尋時 `sources` 是空清單 `[]`（不收答案裡未驗證的網址）；若模型還是搜尋了，記下來、改用別的題目再試 | ☐ |

限制（不是 bug）：隔離模式不是作業系統層級的沙箱，claude 仍然讀得到家目錄（訂閱登入憑證放在那裡）。

簽核：全部通過後在這裡寫日期與驗證者：________
