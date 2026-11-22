# Changelog

格式參考 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-TW/1.1.0/)，版號遵循 [SemVer 2.0.0](https://semver.org/lang/zh-TW/)。
規則全文：全域 `knowledge/conventions/versioning.md`。小改動只動版本號與這份檔案、不打 tag；只有 release 才打 annotated tag `vX.Y.Z`。

## [Unreleased]

## [0.5.0] - 2026-11-23

### Added
- 統一呼叫介面（`INTERFACE_VERSION = "1"`；`github_copilot_login`、`chatgpt_login` 用同一組名字），給多來源的 LLM 函式庫包裝用：
  - `ask()`／`ask_stream()` 的第一個參數可以是訊息清單（`role`＋`content`，content 可為字串或只含文字的 parts）；system 併進系統提示，多輪攤成一段逐字稿。`tool` 角色、圖片、最後一則不是 user 丟 `ValueError`。
  - `flatten_messages(messages, system=None) -> (system, prompt)`。
  - `ClaudeResult.usage`（`{"input", "output", "cached_input"}`）與 `ClaudeResult.model`（實際用的模型，取自 `modelUsage`）。
  - 新的共同基底 `LoginError`（每種錯誤都有 `.kind`）；別名 `Result`、`UsageLimitError`、`AuthError`、`NotInstalledError`、`CallTimeoutError`。
  - `ClaudeUsageLimitError.retry_after`（Claude 只給時刻，目前一律 `None`）。
  - `CAPABILITIES`：能力照實標（沒有 function calling、不收圖、有串流、多輪是攤平的）。
  - `tests/test_interface.py`。
- `ClaudeTimeoutError`（`ClaudeError` 的子類別）：逾時改丟它。

### Changed
- `ask()`／`ask_stream()` 的 `model` 預設改成 `None`（＝`"haiku"`，行為不變）。
- `ClaudeError` 多繼承 `LoginError`、`ClaudeNotFoundError` 多繼承 `LoginError`；舊的 `except` 行為不變（`ClaudeNotFoundError` 仍**不是** `ClaudeError`）。
- **型別細節**：逾時的例外型別從 `ClaudeError` 變成它的子類別 `ClaudeTimeoutError`；`except ClaudeError` 照樣接得到，只有用 `type(e) is ClaudeError` 精確比對的程式要改。`tests/test_isolated.py` 對應的斷言跟著改。

## [0.4.1] - 2026-11-19

### Fixed
- 非串流 `ask(isolated=True)` 逾時或被中斷（含 Ctrl+C／`KeyboardInterrupt`）時，改成連子程序一起結束（Windows 用 `taskkill /T /F`，再補 `kill()`）、等它結束後才刪暫存資料夾。之前靠 `subprocess.run` 逾時只殺得到 npm `claude.cmd` 外層的 cmd.exe，node 會留下來，呼叫可能要等 node 自己結束才回來。一般模式（`isolated=False`）的 `ask()` 不受影響：仍用 `subprocess.run`，回傳、例外種類、錯誤訊息、結束碼都跟 0.4.0 相同。
- `ask_stream()`／`search()` 讀到一半被中斷（Ctrl+C、`on_event` 丟 `BaseException`、讀取錯誤）時，claude 子程序會被結束，不再留在背景、讓隔離模式的暫存資料夾刪不掉；Windows 上逾時與中斷都用 `taskkill /T` 連子程序一起結束（npm 的 `claude.cmd`）。
- 隔離模式的錯誤訊息不再附 claude 的 stderr、`result` 或 stdout 原文（之前子程序失敗、額度用完、錯誤 result 三條路都還會附）；錯誤類別不變。
- 隔離模式的旗標檢查只認 `claude --help` 裡的選項宣告行；只在別的旗標說明裡被提到不再算有支援，`dontAsk` 要出現在 `--permission-mode` 的說明裡。
- 隔離模式拒絕以 `-` 開頭的 `model`／`system`（`ValueError`），避免被 claude 當成另一個旗標。
- `search()` 的來源比對接受網址裡一層成對括號（例如維基百科 `/wiki/Foo_(bar)`），正確的引用不再被丟掉。

### Changed
- **行為改變**：`search()` 在**沒有任何搜尋結果**時（模型沒搜尋、或讀不到搜尋結果的格式），`sources` 回空清單 `[]`，不再退回答案裡未驗證的網址。對呼叫端的影響：這種情況下以前可能拿到幾個來源、現在拿到 `[]`；`sources` 的型別不變，但呼叫端不能假設它一定不是空的（顯示「沒有來源」或改看 `text`）。有搜尋結果時的行為不變（只收引用且出現在結果裡的網址；全都對不上就給全部搜尋結果）。
- 隔離模式不放行 `CLAUDE_CONFIG_DIR`（刻意維持 0.4.0 的白名單）；README 寫明這種情況要改用 `CLAUDE_CODE_OAUTH_TOKEN`（`claude setup-token` 取得）。
- README：補上 `--help` 讀取時間不算在 `timeout` 內、`CLAUDE_CONFIG_DIR` 的處理方式、隔離模式三個呼叫的中斷與逾時都會殺整棵程序樹，以及「引用全對不上時給全部搜尋結果」的實際行為；安裝範例的版本改成 0.4.1。

## [0.4.0] - 2026-11-18

### Added
- 隔離模式：`ask()`／`ask_stream()` 新增 `isolated=False`（預設不變），CLI 新增 `--isolated`。隔離時不讀使用者／專案設定、CLAUDE.md、自動記憶，不載入 MCP、skills、hooks；工具只能是 `""` 或 `WebSearch`、權限模式固定 `dontAsk`；在新開的空暫存資料夾裡跑、跑完刪掉；不保存 session；子程序環境變數改成白名單（不帶其他金鑰）；錯誤訊息不附 claude 的原始輸出。
- 用到的每個旗標都會先到 `claude --help` 確認；這版 claude 不支援時丟新的 `ClaudeIsolationUnsupportedError`（CLI 結束碼 1），不會少帶旗標照跑。
- `search(query, *, isolated=True) -> {"text", "sources"}`：只能上網搜尋的搜尋員；`sources` 只收答案引用、而且真的出現在 WebSearch 結果裡的網址。
- `tests/test_isolated.py`：用假子程序驗證隔離模式的參數、環境、工作目錄與 `search()`（不呼叫 Claude、不連網）。

## [0.3.2] - 2026-11-17

### Fixed
- Windows 上從沒有主控台的 GUI 程式（pythonw、PyInstaller --windowed）呼叫時，每次都會閃出 claude 的主控台視窗：ask() 與 ask_stream() 在 Windows 改用 `CREATE_NO_WINDOW` 啟動子程序（原 0.2.1 的修正，合併進 0.3.x 線；ask_stream 是新增的呼叫點，一併處理）。

## [0.3.1] - 2026-11-12

### Added
- 導入版本號系統（版本來源：claude_subscription.py 的 __version__（最新 tag 為 v0.2.1，0.3.1 尚未打 tag））。以 0.3.1 作為基準版本；此前的歷史不逐版回溯，見 `git log`（共 16 個 commit，第一個在 2026-06-20）。

## 導入前的近期歷史（自 git log 擷取，僅供參考，非正式版本）

- 2026-10-03 fix: 額度用完變成 ClaudeUsageLimitError（帶重置時間），錯誤訊息改用 claude 的 result（v0.3.1）
- 2026-10-03 feat: ask_stream()——用 stream-json 邊跑邊把每個事件交給 on_event（v0.3.0）
- 2026-08-25 README：修正錯誤的能力描述，補上 agent 模式、結束碼契約與實測成本
- 2026-08-25 補上 MIT 授權與完整的套件 metadata
- 2026-08-25 修正 claude-ask.sh 在 python3 是空殼 stub 時無聲失敗
- 2026-08-25 修正範例的 Python 3.9 相容性，並補上 agent 模式與結束碼處理
- 2026-08-25 新增離線測試套件（85 個測試，不花錢、不需網路）
- 2026-08-25 修正結束碼契約與認證判斷，並補上 agent 模式參數
- 2026-07-19 修正：Windows 非 UTF-8 主控台（cp950/cp936）下 --check 會因 ✓/✗ 符號崩潰
- 2026-07-01 新增跨程式整合範本與快速整合指南
- 2026-06-30 新增 .gitattributes：鎖定 .sh 用 LF、.bat 用 CRLF
- 2026-06-30 功能擴充：CLI 啟動器、附檔輸入、session 延續、結構化輸出與完整 API 文件
- 2026-06-20 新增：透過官方 Claude Code CLI 用訂閱/API key 呼叫 Claude 的工具
