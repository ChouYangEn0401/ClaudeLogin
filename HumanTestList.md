# HumanTestList

人要親手做的檢查（真的 CLI、真的登入）。自動測試只用假的子程序，碰不到這些。

隔離模式的真機清單另見 `docs/testing/isolated-mode-checklist.md`（這份只列統一介面 0.5.0 的項目）。

## 待測

- [ ] 2026-11-23 · 訊息清單＋system 真的送到 claude · `python -c "from claude_subscription import ask; r=ask([{'role':'system','content':'只回一個字'},{'role':'user','content':'說好'}]); print(r.text, r.model, r.usage)"` · 回一個字；`model` 是完整模型名（不是空的）；`usage` 有 input／output
- [ ] 2026-11-23 · 多輪訊息攤平後 claude 看得懂 · 用 user→assistant→user 三則（第二個 user 問「我剛剛問了什麼？」）呼叫 `ask` · 回答提到第一則的內容
- [ ] 2026-11-23 · 額度用完時丟的是 `UsageLimitError` · 下次真的遇到額度用完時記下 `type(e).__name__`、`e.resets` · 是 `ClaudeUsageLimitError`，`resets` 有時間
- [ ] 2026-11-23 · 新手教學能照著走完 · 找一台新電腦，照 docs/TUTORIAL.md 從頭走一遍 · 每一步「會看到什麼」都對得上；對不上的記下實際畫面交回改教學
- [ ] 2026-11-23 · 新電腦裝 Claude Code 要不要 Git Bash、PATH 有沒有自動設好 · 在沒裝過 Git 的 Windows 上跑 `irm https://claude.ai/install.ps1 | iex`，重開 PowerShell 後打 `claude --version`；再跑 `claude` 第一次登入 · 記下：有沒有要求先裝 Git／Git Bash（原文）、`claude` 是否直接找得到（找不到時實際裝在哪個資料夾）、第一次執行依序問了哪些問題（佈景主題、登入方式、信任資料夾的實際用詞），交回改教學步驟 3、4

## 測過了

（還沒有）
