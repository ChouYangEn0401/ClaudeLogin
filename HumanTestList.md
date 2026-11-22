# HumanTestList

人要親手做的檢查（真的 CLI、真的登入）。自動測試只用假的子程序，碰不到這些。

隔離模式的真機清單另見 `docs/testing/isolated-mode-checklist.md`（這份只列統一介面 0.5.0 的項目）。

## 待測

- [ ] 2026-11-23 · 訊息清單＋system 真的送到 claude · `python -c "from claude_subscription import ask; r=ask([{'role':'system','content':'只回一個字'},{'role':'user','content':'說好'}]); print(r.text, r.model, r.usage)"` · 回一個字；`model` 是完整模型名（不是空的）；`usage` 有 input／output
- [ ] 2026-11-23 · 多輪訊息攤平後 claude 看得懂 · 用 user→assistant→user 三則（第二個 user 問「我剛剛問了什麼？」）呼叫 `ask` · 回答提到第一則的內容
- [ ] 2026-11-23 · 額度用完時丟的是 `UsageLimitError` · 下次真的遇到額度用完時記下 `type(e).__name__`、`e.resets` · 是 `ClaudeUsageLimitError`，`resets` 有時間

## 測過了

（還沒有）
