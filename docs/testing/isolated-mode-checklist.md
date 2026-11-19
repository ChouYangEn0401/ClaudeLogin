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

限制（不是 bug）：隔離模式不是作業系統層級的沙箱，claude 仍然讀得到家目錄（訂閱登入憑證放在那裡）。

簽核：全部通過後在這裡寫日期與驗證者：________
