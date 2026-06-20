# 用 Claude 訂閱（或 API key）在程式裡呼叫 Claude

讓你的其他程式呼叫 Claude 做資料整理，可走**已付費的訂閱（Pro / Max）**或 **API key**。
核心原理是把**官方 Claude Code 執行檔**當子程序呼叫（`claude -p` headless 模式）——
請求一律「經過官方 Claude Code」，用的就是該台電腦上 Claude Code 設定的登入方式。
零第三方相依套件，跨 Windows / macOS / Linux。

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

> **可選：用 pip 安裝成指令。** 連同 `pyproject.toml` 一起給對方後，在資料夾裡執行
> `pip install .`，就會多一個全域指令 `claude-sub`（= `python claude_subscription.py`）。

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

`ask()` 主要參數：

| 參數 | 預設 | 說明 |
|------|------|------|
| `model` | `"haiku"` | `haiku`(最便宜) / `sonnet`(均衡) / `opus`(最強最貴) 或完整模型名 |
| `system` | 內建精簡提示 | 系統提示；設 `None` 用 Claude Code 預設（**較貴**） |
| `json_schema` | `None` | 給定後強制結構化輸出，用 `r.data` 取得 |
| `max_budget_usd` | `None` | 單次花費上限，超過中止，保護額度 |
| `tools` | `""` | 預設關閉所有工具（純文字進出）。要讓它讀檔/執行指令才改 |
| `auth` | `"subscription"` | 登入方式：`subscription` / `apikey` / `auto` |
| `timeout` | `180` | 逾時秒數 |

---

## 用法二：命令列（任何語言都能 shell out 呼叫）

```powershell
# 直接帶提示
python claude_subscription.py --model haiku "把這段話濃縮成一句：……" --show-cost

# 從檔案讀提示（Windows 上傳中文最穩定，避開 PowerShell 管線編碼問題）
python claude_subscription.py --prompt-file input.txt --json-schema-file schema.json --show-cost

# 走 API key（按量計費）而非訂閱
python claude_subscription.py --auth apikey "整理這段：……"

# 新電腦自我診斷 / 查偵測到的執行檔
python claude_subscription.py --check
python claude_subscription.py --which
```

- 結果印到 **stdout**（用了 `--json-schema-file` 時輸出結構化 JSON）。
- 加 `--show-cost` 會把花費印到 **stderr**（不污染 stdout，方便其他程式 pipe）。
- 你的非 Python 程式（Node / C# / Go…）只要 `spawn` 這個指令、讀 stdout 即可。

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
- `example_usage.py` — 三個資料整理範例（重點整理 / 結構化 JSON / 批次分類）。
- `pyproject.toml` — 選配，讓對方可 `pip install .` 並取得 `claude-sub` 指令。
- `README.md` — 本說明。
