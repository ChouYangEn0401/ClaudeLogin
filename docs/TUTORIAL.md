# 新手教學：用自己的 Claude 訂閱，在程式裡問 Claude 一句話

這份教學寫給**沒什麼電腦概念的人**。照著一步一步做，每一步都寫了「要打什麼」「會看到什麼」「不是這樣怎麼辦」。
完整的功能說明在 [README](../README.md)。

---

## 這是什麼

- 這個套件（名字叫 `claude_subscription`）讓你的 Python 程式可以問 Claude 問題。
- 它不是自己去連 Claude，而是**請你電腦上的官方 Claude Code 去問**，用的是你自己的 Claude 訂閱（Pro／Max）。
- 它不會讀、也不會存你的密碼或登入憑證。

## 你需要準備什麼

| 要準備的 | 說明 |
|---|---|
| 一台 Windows 電腦 | 這份教學以 Windows 10／11 為例 |
| Claude 帳號＋訂閱（Pro 或 Max） | 沒有訂閱也可以改用 API key，見 README 的「登入方式」 |
| 網路 | 安裝與登入都要連網 |
| 大約 20 分鐘 | |

先認識三個詞：

- **終端機**＝打指令的視窗（黑色或藍色底）。Windows 內建的叫 **PowerShell**。
- **指令**＝在終端機裡打的一行字，打完按 Enter 執行。
- **套件**＝別人寫好、可以裝進 Python 的程式。

---

## 步驟

### 步驟 1：打開 PowerShell

1. **做什麼**：開一個終端機視窗。
2. **打什麼**：按鍵盤左下角的 Windows 鍵，打 `PowerShell`，按 Enter。
3. **會看到什麼**：一個視窗，最後一行是 `PS` 開頭、`>` 結尾，中間是你目前所在的資料夾（每台電腦不同），像這樣：

   ```
   PS ...>
   ```

4. **不是這樣怎麼辦**：找不到的話，在「開始」按右鍵，選「Windows PowerShell」或「終端機」。

之後每一步的指令，都是在這個視窗裡打。**一次複製一行**，貼上（在視窗裡按右鍵就是貼上），按 Enter。

### 步驟 2：確認有沒有 Python

1. **做什麼**：看看電腦有沒有裝 Python（一種程式語言，這個套件要靠它跑）。
2. **打什麼**：

   ```powershell
   python --version
   ```

3. **會看到什麼**：`Python 3.` 開頭、後面是數字，例如：

   ```
   Python 3.12.8
   ```

   這個套件 3.9 以上就能跑，但**建議 3.11 或更新**：之後如果要用 ntu_easy_llm 或 LLOP，它們要 3.11，先裝新版就不用重裝。

4. **不是這樣怎麼辦**：
   - 看到 `Python was not found` 或「無法辨識 'python' 詞彙」：還沒裝。到 <https://www.python.org/downloads/> 下載 Windows 安裝檔，
     安裝畫面第一頁**一定要勾「Add python.exe to PATH」**，再按 Install。裝好後**關掉 PowerShell 再開一個新的**，重打一次上面的指令。
   - 版本比 3.11 舊：照上面的方法裝新版。

### 步驟 3：安裝官方 Claude Code

1. **做什麼**：裝 Anthropic 官方的 Claude Code（命令列工具，指令叫 `claude`）。這個套件就是靠它去問 Claude。
2. **打什麼**：

   ```powershell
   irm https://claude.ai/install.ps1 | iex
   ```

3. **會看到什麼**：一段安裝訊息，跑完回到 `PS ...>`。接著**關掉 PowerShell、重開一個**，再打：

   ```powershell
   claude --version
   ```

   會印出一行版本號（一串數字）。

4. **不是這樣怎麼辦**：
   - 重開視窗後 `claude --version` 還是說「無法辨識 'claude' 詞彙」：如果安裝訊息沒有錯誤，可以試著用完整路徑直接執行：

     ```powershell
     & "$HOME\.local\bin\claude.exe" --version
     ```

     有印出版本號的話，代表裝好了、只是 PowerShell 還不知道它在哪。可以把 `$HOME\.local\bin` 加進 PATH（Windows 的「編輯使用者的環境變數」→ `Path` → 新增），
     或重新開機一次再試。（這個資料夾是官方安裝程式常見的位置，以你電腦上的安裝訊息為準。）
     這個套件自己也會去 `$HOME\.local\bin` 找 `claude`，所以就算 PowerShell 找不到，步驟 8 的自我檢查仍可能顯示 `✓ 找到 claude`；
     但步驟 4 要在 PowerShell 打 `claude` 登入，那時就用上面的完整路徑寫法：`& "$HOME\.local\bin\claude.exe"`。
   - 如果出現要你先安裝 Git（或 Git Bash）的錯誤，可以試著裝 Git，裝完**關掉 PowerShell 重開**，再做一次這一步：

     ```powershell
     winget install Git.Git
     ```

     第一次用 winget 時，它可能會用英文問你是否同意條款（結尾是 `[Y] Yes  [N] No`），打 `Y` 按 Enter。
   - 注意：VS Code 的 Claude Code 擴充功能**不會**在 PowerShell 裡加 `claude` 指令，這份教學要的是上面這個命令列版本。

### 步驟 4：在終端機登入 Claude

1. **做什麼**：用你自己的 Claude 帳號登入。登入一次就好，之後這台電腦會記住。
2. **打什麼**：

   ```powershell
   claude
   ```

3. **會看到什麼**：第一次執行會問你幾個問題（實際的字以畫面為準，大概是這幾個）：
   - 先問畫面的佈景主題（顏色）：隨便選一個，按 Enter。
   - 問登入方式：選**用 Claude 帳號登入（訂閱）**那一個，不要選 API key 那一個。
   - 打開瀏覽器：在瀏覽器登入你的 Claude 帳號、按允許，再回到終端機。
   - 問要不要信任目前這個資料夾：選 **Yes**。

   最後畫面會變成可以打字跟 Claude 聊天的樣子。打 `/exit` 按 Enter 離開，回到 `PS ...>`。
4. **不是這樣怎麼辦**：
   - 瀏覽器沒有自己打開：終端機上會有一個網址，把它複製到瀏覽器打開。
   - 這台電腦沒有瀏覽器（例如伺服器）：改用 `claude setup-token`，見 README 的「新電腦設定」。

### 步驟 5：開一個練習用的資料夾

1. **做什麼**：開一個新資料夾，等一下把套件裝在這裡，不會弄亂電腦其他地方。
2. **打什麼**（一次一行）：

   ```powershell
   mkdir $HOME\claude-demo
   ```

   ```powershell
   cd $HOME\claude-demo
   ```

3. **會看到什麼**：第一行會列出新資料夾的資訊（最後一欄是 `claude-demo`）；第二行之後，提示字變成 `...\claude-demo>` 結尾。
4. **不是這樣怎麼辦**：看到「已經存在」的錯誤，代表資料夾早就有了，直接打第二行 `cd` 那行就好。

### 步驟 6：建一個「虛擬環境」並啟用

**虛擬環境**＝一個獨立的 Python 小房間，裝在裡面的套件不會影響電腦其他程式。

1. **做什麼**：建立並進入虛擬環境。
2. **打什麼**（一次一行）：

   ```powershell
   python -m venv .venv
   ```

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. **會看到什麼**：第一行跑幾秒、沒有訊息。第二行之後，提示字最前面多了 `(.venv)`：

   ```
   (.venv) PS ...\claude-demo>
   ```

4. **不是這樣怎麼辦**：
   - 第二行出現紅字，裡面有「**因為這個系統上已停用指令碼執行**」：Windows 預設不讓腳本執行。先打下面這行（只對這個視窗有效，關掉就恢復），再打一次 `.\.venv\Scripts\Activate.ps1`：

     ```powershell
     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
     ```

   - **以後每次重開 PowerShell**，都要先 `cd $HOME\claude-demo`，再打 `.\.venv\Scripts\Activate.ps1`，看到 `(.venv)` 才繼續。

### 步驟 7：安裝這個套件

1. **做什麼**：從這個專案的 GitHub Release 下載並安裝套件。
2. **打什麼**：

   ```powershell
   python -m pip install https://github.com/ChouYangEn0401/ClaudeLogin/releases/download/v0.5.1/claude_subscription-0.5.1-py3-none-any.whl
   ```

3. **會看到什麼**：一些下載訊息，最後一行是：

   ```
   Successfully installed claude-subscription-0.5.1
   ```

4. **不是這樣怎麼辦**：
   - 出現 `No matching distribution` 或連線錯誤：檢查網路；確認整行有完整複製（網址很長）。
   - 出現 `WARNING: You are using pip version ...`：只是提醒 pip 有新版，可以不理它。

### 步驟 8：做一次自我檢查（不花錢）

1. **做什麼**：讓套件檢查「找不找得到 claude」「有沒有登入」。加了 `--no-ping` 就不會真的問 Claude、不花額度。
2. **打什麼**：

   ```powershell
   claude-sub --check --no-ping
   ```

3. **會看到什麼**（`Python` 後面的版本、`claude` 的位置每台電腦不同）：

   ```
   === Claude 訂閱工具 v0.5.1 — 環境檢查 ===
   OS: Windows / Python 3.12.8
   ✓ 找到 claude： …\claude.exe
     訂閱憑證檔（.credentials.json）：有
     CLAUDE_CODE_OAUTH_TOKEN 環境變數：無
     ANTHROPIC_API_KEY 環境變數：無

   ✓ 靜態檢查通過（已用 --no-ping 略過實測呼叫）。
   ```

4. **不是這樣怎麼辦**：
   - `✗ 找不到 claude 執行檔。`：回到步驟 3，裝好後**重開 PowerShell**（記得重新 `cd` 和啟用虛擬環境）。
   - `⚠ 沒看到訂閱憑證檔或 OAuth token 環境變數。` 和 `✗ 未偵測到登入憑證`：回到步驟 4 登入。
   - `claude-sub` 這個字「無法辨識」：提示字前面沒有 `(.venv)`，回到步驟 6 啟用虛擬環境。也可以改打 `python -m claude_subscription --check --no-ping`，效果一樣。

### 步驟 9：真的問 Claude 一句（用指令）

1. **做什麼**：送一句話給 Claude，看它回答。這一步會用掉一點點訂閱額度。
2. **打什麼**：

   ```powershell
   claude-sub "用一句話介紹台北"
   ```

3. **會看到什麼**：等幾秒到十幾秒，畫面印出 Claude 的回答（一句話），然後回到 `(.venv) PS ...>`。
4. **不是這樣怎麼辦**：看下面的「常見問題」，依畫面上的紅字找。

### 步驟 10：真的問 Claude 一句（用 Python 程式）

1. **做什麼**：寫一個三行的小程式，讓程式去問 Claude。
2. **打什麼**：先用記事本開一個新檔：

   ```powershell
   notepad ask.py
   ```

   記事本問「要建立新檔案嗎？」按「是」。把下面三行貼進去，按 Ctrl+S 存檔，關掉記事本：

   ```python
   from claude_subscription import ask
   r = ask("用一句話介紹台北")
   print(r.text)
   ```

   然後執行它：

   ```powershell
   python ask.py
   ```

3. **會看到什麼**：幾秒後印出 Claude 的回答。
4. **不是這樣怎麼辦**：
   - `ModuleNotFoundError: No module named 'claude_subscription'`：虛擬環境沒啟用（前面沒有 `(.venv)`），回到步驟 6。
   - 其他紅字：看最後一行，對照下面的「常見問題」。

---

## 常見問題

| 畫面上看到 | 意思 | 怎麼辦 |
|---|---|---|
| `[claude_subscription] 錯誤：找不到 claude 執行檔。…`（Python 裡是 `ClaudeNotFoundError`） | 沒裝官方 Claude Code，或裝了但這個視窗還不知道 | 做步驟 3，然後重開 PowerShell |
| `[claude_subscription] 認證錯誤：…`（Python 裡是 `ClaudeAuthError`） | 沒登入，或登入過期 | 做步驟 4 重新登入 |
| `Claude 的使用額度用完了：…`（Python 裡是 `ClaudeUsageLimitError`） | 這段時間的訂閱額度用完了 | 等額度重置再用；在 `claude` 裡打 `/status` 可以看額度 |
| 回答很久都沒出來 | 預設最多等 180 秒 | 再試一次；要等更久可加 `--timeout 300` |
| 中文變成亂碼 | 主控台編碼問題 | 先打 `$env:PYTHONUTF8 = "1"` 再執行 |
| 結果好像在按量收費 | 電腦上設了 `ANTHROPIC_API_KEY` | 預設的訂閱模式會自動忽略它；詳見 README 的「三個你必須知道的重點」 |

想在完全不花錢的情況下確認環境，隨時可以打 `claude-sub --check --no-ping`。

---

## 使用聲明（一定要看）

- 這個套件用的是**你自己在這台電腦上登入的個人訂閱**。
- **不推薦拿個人訂閱服務別人**：不要把它拿去轉售、共用，或做成給別人用的服務。
- **條款你自己看**：Claude 有自己的使用條款，某種用法可不可以，請自己讀過、自己負責。
- 本專案只提供技術介面，不代表任何服務商。完整的聲明在 README 的〈訂閱登入的使用聲明〉。

---

## 全部做完了，接下來可以…

- 讀 README 的「用法一：在你的 Python 程式裡 import」：結構化 JSON 輸出、多輪對話、附帶檔案。
- 讀 README 的「用法二：命令列」：別的程式語言也能呼叫 `claude-sub`。
- 需要同時接 Claude、GitHub Copilot、ChatGPT 三家：這三個套件用同一組名字（README 的「給程式呼叫：統一介面」）。
- 想用一份設定檔切換本地模型、API 金鑰、訂閱：看 ntu_easy_llm 的 `remote/subscription/claude` 來源。
