# 用 Claude 訂閱（或 API key）在程式裡呼叫 Claude

讓你的其他程式呼叫 Claude 做資料整理，可走**已付費的訂閱（Pro / Max）**或 **API key**。
核心原理是把**官方 Claude Code 執行檔**當子程序呼叫（`claude -p` headless 模式）——
請求一律「經過官方 Claude Code」，用的就是該台電腦上 Claude Code 設定的登入方式。
零第三方相依套件，跨 Windows / macOS / Linux。

## 這個工具能做 / 不能做

| 能 ✅ | 不能 ❌ |
|------|--------|
| 文字進、文字出（問答、整理、分類、抽取） | **生成圖片**（這條路是文字模型，不產圖。需要的話得另接 API 的圖像模型） |
| 讀入文字檔當輸入（`--attach`，可多檔） | 直接「看」圖片/PDF 內容（headless 文字管線不支援影像輸入） |
| 強制結構化 JSON 輸出（`--json-schema`） | |
| 把答案存成檔案（`--output-file`） | |
| 單次呼叫，或多輪 session 延續對話（記得上下文） | |
| 給程式接（`--format json`，含 `session_id`、`cost`） | |

> 想「產生檔案」其實可行：開啟工具（`--tools default`）後讓 Claude 用 Write 工具在資料夾寫檔，
> 但那會變貴也較複雜，現階段建議用 `--output-file` 存它回的文字即可。

---

## ⚡ 快速整合（給另一支程式，3 種擇一）

> 前提：那台電腦已裝官方 Claude Code 並登入（見下方「新電腦設定」）。先跑一次 `--check` 確認。

**① 另一支程式是 Python → 直接 import（最簡單）**
```python
# 若 claude_subscription.py 不在同資料夾，先 pip install . 或加 sys.path
from claude_subscription import ask
r = ask("把這段整理成三點重點：……")     # 單次
print(r.text, r.cost_usd)
```

**② 任何語言 → 呼叫 CLI，讀 `--format json`（stdout 是乾淨 JSON）**
```bash
python claude_subscription.py --format json "分類情緒：這服務爛透了"
# stdout -> {"text":"negative","session_id":"…","cost_usd":0.0012,...}
```
> 可直接參考 `integration_sample.py`（一個 `call()` 函式，複製即用，含單次與多輪）。

**③ 想要「一個指令」→ 用啟動器**（把資料夾加入 PATH）
```bash
claude-ask "你的提示"            # Windows: claude-ask.bat；mac/Linux: ./claude-ask.sh
```

**拿結果的約定**：答案永遠在 **stdout**、診斷在 **stderr**；`--format json` 回傳
`{text, structured_output, session_id, cost_usd, model, duration_ms}`；
多輪對話把 `session_id` 帶進下一次 `--resume`（第一輪要 `--persist` 或用 `--session`）。

---

## ⚠️ 先讀：三個你必須知道的重點

1. **這不是無限免費算力。** 程式化呼叫會消耗你的訂閱用量 / 額度（2026 年這套計費機制
   官方來回改過數次——曾宣布獨立的每月 Agent SDK 額度 Pro $20 / Max5x $100 / Max20x $200，
   又在 6/16 暫緩）。請當成「有限、會被計量」來用。你那種輕量資料整理（每次約 $0.005～0.01）
   通常無虞，但**批次大量跑前先估算**。隨時用 `/status`（在 Claude Code 內）查目前額度。

2. **合規界線（界線在「請求怎麼到達 Claude」）。**
   - ✅ 透過**官方 `claude` 執行檔**送出（本工具的做法）→ 官方支援，「uses your subscription as intended」。
   - ❌ 把訂閱 OAuth **token 抽出來自己直接打 Anthropic API**（OpenClaw / OpenCode 那類自製 harness）→ **明確禁止**。
   - 散佈給別人：請對方在自己電腦裝官方 Claude Code、用自己帳號登入；**切勿散佈你的 token / 憑證**。
     要大規模 / 商業散佈，最無爭議的是讓每位使用者**自備 API key**（`--auth apikey`）。

3. **登入方式可選（`--auth` / `auth=`）。** 預設 `subscription`：呼叫前會把 `ANTHROPIC_API_KEY` /
   `ANTHROPIC_AUTH_TOKEN` 從子程序環境移除，避免被按量計費「搶走」。要按量計費就用 `apikey`；
   想完全照 Claude Code 既有設定就用 `auto`。

來源：
[Authentication — Claude Code Docs](https://code.claude.com/docs/en/authentication)、
[The Register：澄清第三方工具禁令](https://www.theregister.com/software/2026/02/20/anthropic-clarifies-ban-on-third-party-tool-access-to-claude/)、
[VentureBeat：重新開放（附條件）](https://venturebeat.com/technology/anthropic-reinstates-openclaw-and-third-party-agent-usage-on-claude-subscriptions-with-a-catch)。

---

## 前置需求

- 該台電腦已安裝官方 Claude Code（獨立 CLI 或 VSCode 擴充皆可；工具會自動偵測）。
- 已用自己的帳號登入（訂閱）或設好 API key。
- Python 3.9+（無任何第三方套件相依）。

---

## 📦 把工具給別人用 / 在新電腦上設定

重點觀念：**這個工具不含、也不需要任何人的登入資訊**。它只是去驅動「那台電腦上」官方
Claude Code 的登入。所以發佈時你只要給對方這幾個檔（`claude_subscription.py` 必備，
其餘選配），對方在自己電腦完成下面三步即可——**用的是他自己的訂閱 / API key，跟你的帳號無關**。

**第 1 步：裝官方 Claude Code**

| 系統 | 安裝指令 |
|------|---------|
| Windows (PowerShell) | `irm https://claude.ai/install.ps1 \| iex` |
| macOS / Linux | `curl -fsSL https://claude.ai/install.sh \| bash` |
| 任一系統 | 或在 VS Code 安裝擴充「Anthropic.claude-code」 |

**第 2 步：登入（自己的帳號，二擇一）**

- 一般桌機（有瀏覽器）：執行 `claude`，依提示在瀏覽器登入 Claude.ai 帳號。之後憑證存在
  `~/.claude/.credentials.json`，工具會自動沿用。
- 伺服器 / CI / 無瀏覽器：執行 `claude setup-token` 取得一年效期的 token，設成環境變數
  `CLAUDE_CODE_OAUTH_TOKEN`。**每個人產生自己的，不要共用。**
- 想走按量計費：設好自己的 `ANTHROPIC_API_KEY`，呼叫時加 `--auth apikey`。

**第 3 步：自我診斷**

```bash
python claude_subscription.py --check
```
會檢查：找不找得到 `claude`、登入狀態、並實測一次極小呼叫。全部 ✓ 就能用了。

**第 4 步：讓它「隨處可用」（三選一）**

1. **啟動器腳本（最簡單）**：把本資料夾加入系統 PATH，之後任何位置都能用：
   - Windows：`claude-ask "你的提示"`（用 `claude-ask.bat`）
   - macOS / Linux：`./claude-ask.sh "你的提示"`（先 `chmod +x claude-ask.sh`）
2. **pip 安裝成全域指令**：在資料夾裡 `pip install .`，得到指令 `claude-sub`（= `python claude_subscription.py`）。
3. **直接呼叫**：`python /路徑/claude_subscription.py ...`。

> **登入方式對照**：`--auth subscription`（預設，走訂閱）／`--auth apikey`（走 API key 按量計費）
> ／`--auth auto`（完全照 Claude Code 既有設定，不更動環境變數）。

---

## 用法一：在你的 Python 程式裡 import（最推薦）

純 Python 字串進出，沒有任何編碼問題。

```python
from claude_subscription import ask

# 基本：純文字整理
r = ask("把這段話濃縮成一句重點：……", model="haiku")
print(r.text)
print(r.cost_usd)          # 本次花費（從每月額度扣）

# 結構化輸出：用 JSON Schema 保證格式
schema = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
}
r = ask("把以下分類成清單：……", model="haiku", json_schema=schema, max_budget_usd=0.10)
data = r.data              # 已解析成 Python dict / list
```

多輪對話（session 延續）：

```python
# 第一輪：開新對話，記住 session_id
r1 = ask("我等下要問你問題，先記住我的訂單編號是 A-12345。", persist=True)
sid = r1.session_id

# 後續：用 resume 接續，Claude 記得前面說過的話
r2 = ask("我的訂單編號是多少？", resume=sid)
print(r2.text)   # -> A-12345
```

附帶檔案當輸入：

```python
r = ask("把這份客訴整理成一句重點與急迫度", attach=["ticket.txt"])
```

### `ask()` 完整 API

簽名：`ask(prompt, *, model, system, json_schema, max_budget_usd, tools, timeout, binary, auth, attach, resume, session_id, persist, extra_args) -> ClaudeResult`

| 參數 | 預設 | 說明 |
|------|------|------|
| `prompt` | （必填） | 提示 / 要處理的資料字串 |
| `model` | `"haiku"` | `haiku`(最便宜) / `sonnet`(均衡) / `opus`(最強最貴) 或完整模型名 |
| `system` | 內建精簡提示 | 系統提示；設 `None` 用 Claude Code 預設（**較貴**）。延續對話時自動略過 |
| `json_schema` | `None` | 給定後強制結構化輸出，用 `r.data` 取得 |
| `max_budget_usd` | `None` | 單次花費上限，超過中止，保護額度 |
| `tools` | `""` | 預設關閉所有工具（純文字進出）。要讓它讀檔/執行指令才改 |
| `timeout` | `180` | 逾時秒數 |
| `binary` | 自動偵測 | 自訂 claude 執行檔路徑 |
| `auth` | `"subscription"` | 登入方式：`subscription` / `apikey` / `auto` |
| `attach` | `None` | 文字檔路徑清單，內容會附在提示前 |
| `resume` | `None` | 要延續的 `session_id`（接續舊對話） |
| `session_id` | `None` | 指定固定 session id 開新對話 |
| `persist` | `False` | 保留 session 到磁碟（要日後 resume 就設 True） |
| `extra_args` | `None` | 額外傳給 claude 的參數 list |

回傳 `ClaudeResult`：

| 屬性 | 說明 |
|------|------|
| `.text` | Claude 回的文字 |
| `.data` | 結構化結果（有 `json_schema` 時為已解析物件；否則嘗試解析 `.text`） |
| `.structured_output` | 用 `json_schema` 時的結構化資料 |
| `.cost_usd` | 本次花費（從額度/餘額扣） |
| `.session_id` | 本次 session id（傳給下次 `resume` 即可延續） |
| `.num_turns` / `.duration_ms` / `.raw` | 輪數 / 耗時 / 完整原始 JSON |

失敗時丟 `ClaudeError`（或找不到執行檔時 `FileNotFoundError`）。

---

## 用法二：命令列（任何語言都能 shell out 呼叫）

下面用 `claude-ask` 代表啟動器（= `python claude_subscription.py` 或 `claude-sub`）。

```bash
# 直接帶提示
claude-ask --model haiku "把這段話濃縮成一句：……" --show-cost

# 讀檔當輸入（可多個 --attach），輸出結構化 JSON 並存檔
claude-ask --attach data.txt --json-schema-file schema.json --output-file out.json

# 給程式接：--format json 一次拿到答案 + session_id + 花費
claude-ask --format json "分類這句的情緒：這服務爛透了"

# 多輪對話：第一輪用 --session 指定 id（會自動存檔），之後用 --resume 接續
# （或第一輪用 --persist，再從輸出的 session_id 拿去 --resume）
claude-ask --session 11111111-1111-1111-1111-111111111111 "記住我的代號是 X9"
claude-ask --resume  11111111-1111-1111-1111-111111111111 "我的代號是什麼？"

# 走 API key（按量計費）而非訂閱
claude-ask --auth apikey "整理這段：……"

# 新電腦自我診斷 / 查偵測到的執行檔
claude-ask --check
claude-ask --which
```

### CLI 參數總覽

| 參數 | 說明 |
|------|------|
| `prompt`（位置參數） | 提示文字；中文可直接放在引號內（argv 在 Windows 也安全） |
| `--prompt-file FILE` | 從檔案讀提示（UTF-8，可含 BOM） |
| `--attach FILE` | 附帶文字檔當輸入，可重複多次 |
| `--model` | `haiku`(預設) / `sonnet` / `opus` 或完整模型名 |
| `--system` / `--no-system` | 自訂系統提示 / 改用 Claude Code 預設（較貴） |
| `--json-schema-file FILE` | 強制結構化 JSON 輸出 |
| `--max-budget-usd N` | 單次花費上限 |
| `--tools` | 預設 `""`(全關)；`default`(全開)；或 `Read,Bash` |
| `--auth` | `subscription`(預設) / `apikey` / `auto` |
| `--resume SESSION_ID` | 延續指定對話 |
| `--continue` | 延續本資料夾最近一次對話 |
| `--session UUID` | 指定固定 session id 開新對話（方便日後 resume） |
| `--persist` | 保留 session 到磁碟（單次預設不保留） |
| `--format` | `text`(預設) / `json`（含 `session_id`、`cost`） |
| `--output-file FILE` | 把答案另存到檔案 |
| `--show-cost` | 在 stderr 印出花費 |
| `--check` / `--which` | 自我診斷 / 印出偵測到的執行檔 |

**輸出約定（給其他程式接的關鍵）**：
- 答案一律印到 **stdout**；診斷（花費、session）印到 **stderr**——所以 pipe stdout 永遠拿到乾淨結果。
- `--format json` 時 stdout 是一個 JSON 物件：`{"text", "structured_output", "session_id", "cost_usd", "model", "duration_ms"}`。
- 結束碼：成功 `0`、呼叫失敗 `1`、找不到執行檔 `2`、未登入 `3`。

### 範例：用 Node.js（或任何語言）接

```js
const { execFileSync } = require("node:child_process");

function ask(prompt, { sessionId, persist } = {}) {
  const args = ["claude_subscription.py", "--format", "json", prompt];
  if (sessionId) args.push("--resume", sessionId);
  if (persist) args.push("--persist");          // 多輪對話第一輪要加，才會存檔
  const out = execFileSync("python", args, { encoding: "utf-8" });
  return JSON.parse(out);   // { text, session_id, cost_usd, ... }
}

const r1 = ask("記住我的訂單編號 A-12345", { persist: true });
const r2 = ask("我的訂單編號是？", { sessionId: r1.session_id });
console.log(r2.text);       // -> A-12345
```

---

## 省錢技巧（直接影響你的每月額度）

1. **選便宜模型**：預設 `haiku` 即可應付絕大多數資料整理。實測：叫 Opus 回一句話花 $0.17，
   換 Haiku + 精簡系統提示只花 $0.016（約 1/10）。
2. **保持 `tools=""`**：純文字進出最便宜，也不會去動你的檔案。
3. **保留內建精簡系統提示**：別把 `system` 設 `None`（會載入 Claude Code 那一大包預設提示，很貴）。
4. **設 `max_budget_usd`**：給每次呼叫一個上限，避免意外把額度燒光。
5. **批次時自己累計 `r.cost_usd`**，掌握額度消耗。

---

## 踩雷排解

| 症狀 | 原因 / 解法 |
|------|------------|
| `找不到 claude 執行檔` | 先 `--check` 看指引；裝官方 Claude Code，或設 `CLAUDE_BINARY` 指向 `claude(.exe)` |
| 新電腦不確定有沒有裝好/登入 | 跑 `python claude_subscription.py --check` |
| PowerShell 用 `\|` 管中文進去變亂碼 | PowerShell 5.1 管線預設非 UTF-8。改用 `--prompt-file` 或 `--prompt` 參數 |
| 結果突然變貴 / 像按量計費 | 檢查是否設了 `ANTHROPIC_API_KEY`（`echo $env:ANTHROPIC_API_KEY`）。本工具會自動忽略它，但請確認沒在別處被用到 |
| 回傳 `Claude 回報錯誤` | 多半是額度用完或未登入。開 Claude Code 跑 `/status` 確認登入方式與額度 |
| 主控台中文顯示亂碼 | 執行前設 `$env:PYTHONUTF8 = "1"` |

---

## 檔案

- `claude_subscription.py` — 核心函式庫 + 命令列工具（**發佈必備，且零相依套件**）。
- `claude-ask.bat` — Windows 啟動器（加入 PATH 後可在任何位置用 `claude-ask`）。
- `claude-ask.sh` — macOS / Linux 啟動器。
- `example_usage.py` — Python import 範例（重點整理 / 結構化 JSON / 批次分類 / session 延續）。
- `integration_sample.py` — **另一支程式用 subprocess 呼叫 CLI 的範本**（複製 `call()` 即用）。
- `pyproject.toml` — 選配，讓對方可 `pip install .` 並取得 `claude-sub` 指令。
- `README.md` — 本說明。
