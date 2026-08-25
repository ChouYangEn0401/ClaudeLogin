# 用 Claude 訂閱（或 API key）在程式裡呼叫 Claude

讓你的其他程式呼叫 Claude，可走**已付費的訂閱（Pro / Max）**或 **API key**。
核心原理是把**官方 Claude Code 執行檔**當子程序呼叫（`claude -p` headless 模式）——
請求一律「經過官方 Claude Code」，用的就是該台電腦上 Claude Code 設定的登入方式。
零第三方相依套件，跨 Windows / macOS / Linux。

```
你的程式 → claude_subscription.py → subprocess → claude(.exe) -p → Anthropic
                                                  ↑
                                    帳號與計費在這裡決定，本工具完全不碰你的 token
```

這個區別很重要：**它不是在打 API，它是在遙控官方 CLI**。這既是它合規的原因（見下方
「合規界線」），也是它能力邊界的來源——`claude -p` 能做的，它幾乎都能做。

---

## 這個工具能做 / 不能做

預設模式（`--tools ""`，工具全關）是一個**純文字進出**的便宜管道：

| 能 | 不能（在預設模式下） |
|------|--------|
| 文字進、文字出（問答、整理、分類、抽取） | 生成圖片（這條路是文字模型，不產圖） |
| 讀入文字檔當輸入（`--attach`，可多檔） | 讀取二進位檔——`--attach` 只吃 UTF-8 純文字 |
| 強制結構化 JSON 輸出（`--json-schema-file`） | 讀寫你的檔案、執行指令（工具是關的） |
| 把答案存成檔案（`--output-file`） | |
| 單次呼叫，或多輪 session 延續對話（記得上下文） | |
| 給程式接（`--format json`，含 `session_id`、`cost`） | |

**但把工具打開，它就是完整的 agent**——右欄那些「不能」除了產圖之外都會變成「能」。
見下一節。

---

## 🤖 agent 模式：讓它讀檔、寫檔、看圖片、執行指令

`--tools` 預設是 `""`（全關），所以平常它退化成一個純文字 API。打開之後它就變回
一個完整的 Claude Code agent。以下數字都是本機實測（haiku 模型）：

| 做什麼 | 怎麼叫 | 結果 | 花費 |
|---|---|---|---|
| 純文字（預設） | `--tools ""` | 回文字 | **$0.0015** |
| 讀檔 | `--tools Read` | 讀到檔案內容 | $0.013 |
| **看圖片** | `--tools Read` 讀一張 PNG | 正確答出圖片顏色——**它有視覺** | $0.006 |
| 寫檔（只開工具） | `--tools default` | ❌ **被權限擋下**，檔案沒建立 | $0.070 |
| **寫檔（成功）** | `--tools default --permission-mode acceptEdits` | ✅ 檔案真的被建立，跑了 4 個 turn | $0.024 |

```bash
# 讓 Claude 在指定資料夾裡整理檔案（會真的動手改檔案）
claude-sub --tools default --permission-mode acceptEdits --cwd ./workspace \
           --max-budget-usd 0.20 \
           "把 C:/workspace/raw.csv 讀進來，整理成 C:/workspace/clean.csv"
```

### 四個一定要知道的細節

**① 只開 `--tools` 不夠，還要 `--permission-mode`。**
headless 模式沒辦法跳出來問你「要不要允許寫入」，所以寫檔類工具預設會被擋下。
它會禮貌地回你「I cannot complete this task in a non-interactive session」——
而且**這一次失敗仍然要收費**（實測 $0.07，比成功那次還貴）。要能改檔案就加
`--permission-mode acceptEdits`。

**② 它會在「呼叫你程式的那個目錄」動手。**
子程序繼承 cwd，所以哪支程式呼叫它、它就在那支程式的資料夾裡讀寫。
**開工具時請務必用 `--cwd`（或 `ask(cwd=...)`）把它關進指定資料夾。**

**③ 覆寫系統提示的副作用：它不知道自己在哪。**
本工具預設會塞一個精簡系統提示（省錢用），代價是 Claude Code 那些「你的工作目錄是
X」的動態資訊不會被載入。實測它會回你「請給我絕對路徑」。所以 agent 任務的提示裡
**要寫絕對路徑**，或改用 `--no-system`（但那會貴很多）。

**④ 成本是 15～45 倍。**
agent 要跑多輪、要載入工具定義。預設值（工具全關 + 精簡系統提示）是刻意的省錢設計，
需要時再單次打開就好。開工具時**一定要配 `--max-budget-usd`**。

> 想「產生檔案」但不想付 agent 的錢：用 `--output-file` 把它回的文字存起來就好，
> 那是純文字模式，便宜 15 倍。

---

## ⚡ 快速整合（給另一支程式，3 種擇一）

> 前提：那台電腦已裝官方 Claude Code 並登入（見下方「新電腦設定」）。先跑一次 `--check` 確認。

**① 另一支程式是 Python → 直接 import（最簡單）**
```python
from claude_subscription import ask
r = ask("把這段整理成三點重點：……")     # 單次
print(r.text, r.cost_usd)
```

**② 任何語言 → 呼叫 CLI，讀 `--format json`（stdout 是乾淨 JSON）**
```bash
python claude_subscription.py --format json "分類情緒：這服務爛透了"
# stdout -> {"text":"negative","session_id":"…","cost_usd":0.0012,...}
```
> 可直接參考 `integration_sample.py`（一個 `call()` 函式，複製即用，含單次、多輪、
> agent 模式與結束碼處理）。

**③ 想要「一個指令」→ `pip install` 或用啟動器**
```bash
pip install claude_subscription-0.2.0-py3-none-any.whl
claude-sub "你的提示"
```

**拿結果的約定**：答案永遠在 **stdout**、診斷在 **stderr**；`--format json` 回傳
`{text, structured_output, session_id, cost_usd, model, duration_ms}`；
多輪對話把 `session_id` 帶進下一次 `--resume`（第一輪要 `--persist` 或用 `--session`）。

### 結束碼契約（其他語言分辨失敗原因的關鍵）

| 碼 | 意思 | 你該怎麼處理 |
|---|------|------|
| `0` | 成功 | — |
| `1` | 呼叫失敗（額度用完、逾時、模型錯誤、輸出無法解析） | 可以重試 |
| `2` | 找不到 claude 執行檔 | 對方沒裝 Claude Code，請他安裝 |
| `3` | 未登入 / 認證失敗（token 過期、API key 無效） | 請對方用自己的帳號登入 |
| `4` | 參數或輸入檔錯誤（附檔不存在、schema 壞掉、旗標打錯） | 呼叫端的 bug |

`2` 和 `3` 是「對方的環境要處理」，`1` 是「可以重試」，`4` 是「你的程式有 bug」。

---

## ⚠️ 先讀：三個你必須知道的重點

1. **這不是無限免費算力。** 程式化呼叫會消耗你的訂閱用量 / 額度（2026 年這套計費機制
   官方來回改過數次——曾宣布獨立的每月 Agent SDK 額度 Pro $20 / Max5x $100 / Max20x $200，
   又在 6/16 暫緩）。請當成「有限、會被計量」來用。輕量資料整理（每次約 $0.0015～0.01）
   通常無虞，但**批次大量跑或開 agent 前先估算**。隨時用 `/status`（在 Claude Code 內）查額度。

2. **合規界線（界線在「請求怎麼到達 Claude」）。**
   - ✅ 透過**官方 `claude` 執行檔**送出（本工具的做法）→ 官方支援，「uses your subscription as intended」。
   - ❌ 把訂閱 OAuth **token 抽出來自己直接打 Anthropic API**（OpenClaw / OpenCode 那類自製 harness）→ **明確禁止**。
   - 散佈給別人：請對方在自己電腦裝官方 Claude Code、用自己帳號登入；**切勿散佈你的 token / 憑證**。
     要大規模 / 商業散佈，最無爭議的是讓每位使用者**自備 API key**（`--auth apikey`）。

3. **登入方式可選（`--auth` / `auth=`）。** 預設 `subscription` 會在呼叫前清掉子程序環境裡的
   `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`（避免被按量計費搶走），**以及**
   `CLAUDE_CODE_USE_BEDROCK` / `CLAUDE_CODE_USE_VERTEX` / `CLAUDE_CODE_USE_FOUNDRY` /
   `ANTHROPIC_BASE_URL` 這類會把請求整個導去別家供應商的變數。要按量計費就用 `apikey`
   （該模式**不會**清掉 base URL，方便走自架 proxy / Bedrock / Vertex）；想完全照
   Claude Code 既有設定就用 `auto`。

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
Claude Code 的登入。所以你只要把套件給對方，對方在自己電腦完成下面三步即可——
**用的是他自己的訂閱 / API key，跟你的帳號無關**。

**第 1 步：裝官方 Claude Code**

| 系統 | 安裝指令 |
|------|---------|
| Windows (PowerShell) | `irm https://claude.ai/install.ps1 \| iex` |
| macOS / Linux | `curl -fsSL https://claude.ai/install.sh \| bash` |
| 任一系統 | 或在 VS Code 安裝擴充「Anthropic.claude-code」 |

**第 2 步：登入（自己的帳號，二擇一）**

- 一般桌機（有瀏覽器）：執行 `claude`，依提示在瀏覽器登入 Claude.ai 帳號。之後憑證存在
  `~/.claude/.credentials.json`（macOS 可能改存 Keychain），工具會自動沿用。
- 伺服器 / CI / 無瀏覽器：執行 `claude setup-token` 取得一年效期的 token，設成環境變數
  `CLAUDE_CODE_OAUTH_TOKEN`。**每個人產生自己的，不要共用。**
- 想走按量計費：設好自己的 `ANTHROPIC_API_KEY`，呼叫時加 `--auth apikey`。

**第 3 步：自我診斷**

```bash
claude-sub --check              # 含一次極小的實測呼叫（約 $0.0015）
claude-sub --check --no-ping    # 只做靜態檢查，完全不花錢（適合 CI）
```
會檢查：找不找得到 `claude`、登入狀態、有沒有被第三方供應商變數導走、並實測一次呼叫。

**第 4 步：讓它「隨處可用」（三選一）**

1. **pip 安裝（最推薦）**：`pip install claude_subscription-0.2.0-py3-none-any.whl`，
   得到全域指令 `claude-sub`。跨平台指令名一致，不用改 PATH。
2. **啟動器腳本**：把本資料夾加入系統 PATH。**注意 wheel 裡不含這兩個檔**，
   要用得從原始碼資料夾拿：
   - Windows：`claude-ask "你的提示"`（用 `claude-ask.bat`）
   - macOS / Linux：`./claude-ask.sh "你的提示"`（先 `chmod +x claude-ask.sh`）
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

agent 模式（會真的改檔案）：

```python
r = ask(
    "把 /abs/path/raw.csv 讀進來，整理後寫到 /abs/path/clean.csv",
    tools="default",
    permission_mode="acceptEdits",   # 少了這個，寫檔會被權限擋下
    cwd="/abs/path",                 # 把它關進指定資料夾
    max_budget_usd=0.20,             # agent 模式一定要設上限
)
```

### `ask()` 完整 API

簽名：`ask(prompt, *, model, system, json_schema, max_budget_usd, tools, permission_mode,
timeout, binary, auth, attach, resume, session_id, persist, cwd, extra_args) -> ClaudeResult`

| 參數 | 預設 | 說明 |
|------|------|------|
| `prompt` | （必填） | 提示 / 要處理的資料字串 |
| `model` | `"haiku"` | `haiku`(最便宜) / `sonnet`(均衡) / `opus`(最強最貴) 或完整模型名 |
| `system` | 內建精簡提示 | 系統提示；設 `None` 用 Claude Code 預設（**較貴**）。延續對話時自動略過。**覆寫會讓 Claude 不知道自己在哪個資料夾** |
| `json_schema` | `None` | 給定後強制結構化輸出，用 `r.data` 取得 |
| `max_budget_usd` | `None` | 單次花費上限，超過中止，保護額度 |
| `tools` | `""` | 預設關閉所有工具（純文字進出）。`"default"` 全開，或 `"Read,Bash"` |
| `permission_mode` | `None` | 工具權限模式。要真的能改檔案請設 `"acceptEdits"` |
| `timeout` | `180` | 逾時秒數 |
| `binary` | 自動偵測 | 自訂 claude 執行檔路徑 |
| `auth` | `"subscription"` | 登入方式：`subscription` / `apikey` / `auto` |
| `attach` | `None` | 文字檔路徑清單，內容會附在提示前（只吃 UTF-8 純文字） |
| `resume` | `None` | 要延續的 `session_id`（每輪重送完整歷史，會越來越貴） |
| `session_id` | `None` | 指定固定 session id 開新對話 |
| `persist` | `False` | 保留 session 到磁碟（要日後 resume 就設 True） |
| `cwd` | `None` | claude 的工作目錄。**開工具時務必指定** |
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

例外階層（對應結束碼）：

| 例外 | 意思 | 結束碼 |
|------|------|------|
| `ClaudeNotFoundError`（繼承 `FileNotFoundError`） | 找不到 claude 執行檔 | 2 |
| `ClaudeAuthError`（繼承 `ClaudeError`） | 沒登入 / token 過期 / API key 無效 | 3 |
| `ClaudeError` | 其他呼叫失敗 | 1 |
| `FileNotFoundError` / `ValueError` | 附檔不存在、附檔非文字、參數不合法 | 4 |

---

## 用法二：命令列（任何語言都能 shell out 呼叫）

下面用 `claude-sub` 代表安裝後的指令（也可用 `python claude_subscription.py` 或啟動器 `claude-ask`）。

```bash
# 直接帶提示
claude-sub --model haiku "把這段話濃縮成一句：……" --show-cost

# 讀檔當輸入（可多個 --attach），輸出結構化 JSON 並存檔
claude-sub --attach data.txt --json-schema-file schema.json --output-file out.json

# 給程式接：--format json 一次拿到答案 + session_id + 花費
claude-sub --format json "分類這句的情緒：這服務爛透了"

# 多輪對話：第一輪用 --session 指定 id（會自動存檔），之後用 --resume 接續
claude-sub --session 11111111-1111-1111-1111-111111111111 "記住我的代號是 X9"
claude-sub --resume  11111111-1111-1111-1111-111111111111 "我的代號是什麼？"

# agent 模式：真的讀寫檔案
claude-sub --tools default --permission-mode acceptEdits --cwd ./work \
           --max-budget-usd 0.20 "整理 C:/work/raw.csv 成 C:/work/clean.csv"

# 透傳任意參數給官方 claude（可重複）
claude-sub --claude-arg --add-dir --claude-arg /data "……"

# 提示以 - 開頭時，用 -- 分隔
claude-sub -- "-這是提示不是旗標"

# 走 API key（按量計費）而非訂閱
claude-sub --auth apikey "整理這段：……"

# 新電腦自我診斷 / 查偵測到的執行檔 / 查版本
claude-sub --check
claude-sub --check --no-ping     # 不花錢
claude-sub --which
claude-sub --version
```

### CLI 參數總覽

| 參數 | 說明 |
|------|------|
| `prompt`（位置參數） | 提示文字；中文可直接放在引號內（argv 在 Windows 也安全）。以 `-` 開頭時前面加 `--` |
| `--prompt-file FILE` | 從檔案讀提示（UTF-8，可含 BOM） |
| `--attach FILE` | 附帶文字檔當輸入，可重複多次。只吃 UTF-8 純文字 |
| `--model` | `haiku`(預設) / `sonnet` / `opus` 或完整模型名 |
| `--system` / `--no-system` | 自訂系統提示 / 改用 Claude Code 預設（較貴但它會知道 cwd） |
| `--json-schema-file FILE` | 強制結構化 JSON 輸出 |
| `--max-budget-usd N` | 單次花費上限 |
| `--auth` | `subscription`(預設) / `apikey` / `auto` |
| `--timeout N` | 逾時秒數（預設 180） |
| `--binary PATH` | 自訂 claude 執行檔路徑 |
| **agent 模式** | |
| `--tools` | 預設 `""`(全關)；`default`(全開)；或 `Read,Bash` |
| `--permission-mode` | `acceptEdits` / `auto` / `bypassPermissions` / `manual` / `dontAsk` / `plan`。**不設的話寫檔會被擋** |
| `--cwd DIR` | claude 的工作目錄。開工具時務必指定 |
| `--claude-arg ARG` | 直接透傳一個參數給官方 claude（可重複） |
| **session** | |
| `--resume SESSION_ID` | 延續指定對話 |
| `--continue` | 延續本資料夾最近一次對話 |
| `--session UUID` | 指定固定 session id 開新對話 |
| `--persist` | 保留 session 到磁碟（單次預設不保留） |
| （以上三個 session 旗標互斥） | |
| **輸出 / 診斷** | |
| `--format` | `text`(預設) / `json`（含 `session_id`、`cost`） |
| `--output-file FILE` | 把 stdout 內容另存成檔案。搭配 `--format json` 時存的是整個 JSON 物件 |
| `--show-cost` | 在 stderr 印出花費 |
| `--check` / `--no-ping` | 自我診斷 / 略過實測呼叫（不花錢） |
| `--which` / `--version` | 印出偵測到的執行檔 / 版本號 |

**輸出約定（給其他程式接的關鍵）**：
- 答案一律印到 **stdout**；診斷（花費、session）印到 **stderr**——所以 pipe stdout 永遠拿到乾淨結果。
- `--format json` 時 stdout 是一個 JSON 物件：`{"text", "structured_output", "session_id", "cost_usd", "model", "duration_ms"}`。
- 結束碼見上方「結束碼契約」。

### 範例：用 Node.js（或任何語言）接

```js
const { execFileSync } = require("node:child_process");

const REASONS = {
  1: "呼叫失敗，可重試",
  2: "對方沒裝 Claude Code",
  3: "對方未登入",
  4: "參數錯誤（我的 bug）",
};

function ask(prompt, { sessionId, persist } = {}) {
  const args = ["--format", "json", prompt];
  if (sessionId) args.push("--resume", sessionId);
  if (persist) args.push("--persist");          // 多輪對話第一輪要加，才會存檔
  try {
    return JSON.parse(execFileSync("claude-sub", args, { encoding: "utf-8" }));
  } catch (e) {
    throw new Error(`${REASONS[e.status] ?? "未知錯誤"}: ${e.stderr}`);
  }
}

const r1 = ask("記住我的訂單編號 A-12345", { persist: true });
const r2 = ask("我的訂單編號是？", { sessionId: r1.session_id });
console.log(r2.text);       // -> A-12345
```

---

## 省錢技巧（直接影響你的每月額度）

1. **選便宜模型**：預設 `haiku` 即可應付絕大多數資料整理。實測：叫 Opus 回一句話花 $0.17，
   換 Haiku + 精簡系統提示只花 $0.0015～0.016。
2. **保持 `tools=""`**：純文字進出最便宜，也不會去動你的檔案。開 agent 是 15～45 倍。
3. **保留內建精簡系統提示**：別把 `system` 設 `None`（會載入 Claude Code 那一大包預設提示，很貴）。
4. **設 `max_budget_usd`**：給每次呼叫一個上限，避免意外把額度燒光。開 agent 時尤其必要。
5. **`resume` 不是免費的**：每一輪都會重送完整對話歷史。實測第一輪 $0.0017、第二輪 $0.0147
   （**8.5 倍**）。長對話請考慮自己把上下文濃縮後開新 session。
6. **agent 被權限擋下也要收費**：實測失敗的那次花了 $0.07，比成功的 $0.024 還貴。
   要開工具就一次設對 `--permission-mode`。
7. **批次時自己累計 `r.cost_usd`**，掌握額度消耗。
8. **`--check --no-ping`** 在 CI 裡做環境檢查，完全不花錢。

---

## 🧪 測試

離線測試套件，全程 mock 掉 `subprocess.run`，**不會真的呼叫 Claude、不花任何錢、
不需要網路**，也不需要本機裝過 Claude Code：

```bash
python -m unittest discover -s tests -v
```

85 個測試，涵蓋命令列組裝、auth 環境變數清理、失敗分類、結束碼契約、輸出格式、
agent 參數透傳與 `check_setup` 的所有分支。用標準庫 `unittest`，不需要裝 pytest
（維持零相依）。

---

## 踩雷排解

| 症狀 | 原因 / 解法 |
|------|------------|
| `找不到 claude 執行檔`（exit 2） | 先 `--check` 看指引；裝官方 Claude Code，或設 `CLAUDE_BINARY` 指向 `claude(.exe)` |
| 認證錯誤（exit 3） | 開 Claude Code 跑 `/status` 確認登入方式與額度；或重跑 `claude setup-token` |
| 新電腦不確定有沒有裝好/登入 | 跑 `claude-sub --check` |
| 開了 `--tools` 但它說 "cannot complete in a non-interactive session" | 少了 `--permission-mode acceptEdits` |
| 開了工具但它說「請給我絕對路徑」 | 系統提示被覆寫，它不知道 cwd。提示裡改用絕對路徑，或加 `--no-system` |
| Claude 在錯誤的資料夾動檔案 | 它繼承呼叫端的 cwd。用 `--cwd` 限定 |
| `--claude-arg --add-dir` 報 expected one argument | 已修正（會自動改寫成 `=` 形式）；也可直接寫 `--claude-arg=--add-dir` |
| 執行 `claude-sub` 沒反應像當機 | 舊版會靜默等 stdin。現在會直接報錯提示要給提示文字 |
| `claude-ask.sh` 無聲失敗回 exit 49 | Git Bash for Windows 的 `python3` 是 Microsoft Store 空殼 stub。啟動器已改成實測後自動改用 `python` |
| PowerShell 用 `\|` 管中文進去變亂碼 | PowerShell 5.1 管線預設非 UTF-8。改用 `--prompt-file` 或位置參數 |
| 結果突然變貴 / 像按量計費 | 檢查是否設了 `ANTHROPIC_API_KEY`（`echo $env:ANTHROPIC_API_KEY`）。`--auth subscription` 會自動忽略它 |
| 明明是訂閱卻走到 Bedrock/Vertex | 檢查 `CLAUDE_CODE_USE_BEDROCK` 等變數。`--auth subscription` 會清掉，`--check` 也會警告 |
| 主控台中文顯示亂碼 | 執行前設 `$env:PYTHONUTF8 = "1"`（啟動器腳本已自動設） |

---

## 建置 wheel

```bash
python -m venv .venv
./.venv/Scripts/python -m pip install build      # macOS/Linux: ./.venv/bin/python
./.venv/Scripts/python -m build --wheel
# -> dist/claude_subscription-0.2.0-py3-none-any.whl
```

產出的 wheel 是 `py3-none-any`（純 Python、跨平台通用），**零相依**，內容只有
`claude_subscription.py` 加上 metadata——範例、測試、啟動器都不會被打包進去。
版本號的唯一真實來源是 `claude_subscription.__version__`。

---

## 檔案

- `claude_subscription.py` — 核心函式庫 + 命令列工具（**發佈必備，且零相依套件**）。
- `tests/test_claude_subscription.py` — 離線測試套件（不花錢、不需網路）。
- `claude-ask.bat` — Windows 啟動器（加入 PATH 後可在任何位置用 `claude-ask`）。
- `claude-ask.sh` — macOS / Linux 啟動器。
- `example_usage.py` — Python import 範例（重點整理 / 結構化 JSON / 批次分類 / session 延續 / agent 寫檔）。
- `integration_sample.py` — **另一支程式用 subprocess 呼叫 CLI 的範本**（複製 `call()` 即用，含結束碼處理）。
- `pyproject.toml` — 打包設定，`pip install .` 後可用 `claude-sub` 指令。
- `LICENSE` — MIT。
- `README.md` — 本說明。

---

## 授權

MIT License — 見 [LICENSE](LICENSE)。

本專案本身只是官方 Claude Code 的驅動程式，**不含任何憑證**。你對 Claude 的使用
仍受 Anthropic 的服務條款約束。
