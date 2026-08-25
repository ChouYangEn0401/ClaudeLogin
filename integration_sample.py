# -*- coding: utf-8 -*-
"""
integration_sample.py
=====================
示範「另一支程式」如何呼叫本 CLI 拿到結果——**用 subprocess，不需要 import 本專案、
也不需要 pip install**。把這個 `call()` 函式複製到你的程式裡就能用。

要點：
  * 用 `--format json`：stdout 會是一個乾淨的 JSON 物件（答案 + session_id + 花費）。
  * 答案在 stdout、診斷在 stderr，所以直接 json.loads(stdout) 即可。
  * 結束碼分辨失敗原因：
        0 成功
        1 呼叫失敗（額度用完、逾時、模型錯誤）
        2 找不到 claude 執行檔（對方沒裝 Claude Code）
        3 未登入 / 認證失敗（token 過期、API key 無效）
        4 參數或輸入檔錯誤（你這邊叫錯了）
    2 跟 3 是「對方環境要處理」，1 是「可以重試」，4 是「你的程式有 bug」。

執行：  python integration_sample.py
"""

from __future__ import annotations  # 讓 str | None 這種寫法在 Python 3.9 也能用

import json
import os
import subprocess
import sys
from pathlib import Path

# 本 CLI 的位置。三種寫法擇一：
#   (A) 指向同/已知資料夾的 claude_subscription.py（本範例用這個，最不依賴環境）
#   (B) 已 pip install：CLI = ["claude-sub"]
#   (C) 已把資料夾加入 PATH：CLI = ["claude-ask"]      # Windows 用 claude-ask.bat
HERE = Path(__file__).resolve().parent
CLI = [sys.executable, str(HERE / "claude_subscription.py")]

# 結束碼 → 人看得懂的原因。跟 claude_subscription.EXIT_* 對應。
EXIT_REASONS = {
    1: "呼叫失敗（額度、逾時或模型錯誤）——可以重試",
    2: "找不到 claude 執行檔——請對方安裝官方 Claude Code",
    3: "未登入或認證失敗——請對方執行 `claude` 登入自己的帳號",
    4: "參數或輸入檔錯誤——呼叫端的問題",
}


class ClaudeCliError(RuntimeError):
    """CLI 回報失敗。`exit_code` 可用來分辨該重試還是該叫使用者去設定環境。"""

    def __init__(self, exit_code: int, detail: str):
        self.exit_code = exit_code
        self.detail = detail
        reason = EXIT_REASONS.get(exit_code, "未知錯誤")
        super().__init__(f"[exit {exit_code}] {reason}\n{detail}")


def call(
    prompt: str,
    *,
    model: str = "haiku",
    resume: str | None = None,
    persist: bool = False,
    attach: list[str] | None = None,
    json_schema_file: str | None = None,
    auth: str = "subscription",
    max_budget_usd: float | None = None,
    tools: str = "",
    permission_mode: str | None = None,
    cwd: str | None = None,
    timeout: int = 180,
) -> dict:
    """呼叫本 CLI，回傳 dict：{text, structured_output, session_id, cost_usd, model, duration_ms}。

    多輪對話：第一輪帶 persist=True（才會存檔），拿回傳的 session_id；
              後續帶 resume=session_id 即可延續（Claude 記得前面說過的話）。
              注意每輪都會重送完整歷史，成本隨輪數累加。
    attach：文字檔路徑清單，內容會被當輸入。只吃純文字檔。
    tools / permission_mode / cwd：agent 模式。預設 tools="" 是純文字進出（最便宜）。
              要讓 Claude 真的讀寫檔案，需要 tools="default" 加上
              permission_mode="acceptEdits"，並用 cwd 限定它的工作目錄。
              agent 模式實測成本是純文字的 15～45 倍，務必搭配 max_budget_usd。

    失敗時丟 ClaudeCliError，可從 .exit_code 判斷該怎麼處理。
    """
    args = list(CLI) + ["--format", "json", "--model", model, "--auth", auth]
    if resume:
        args += ["--resume", resume]
    if persist:
        args += ["--persist"]
    for f in attach or []:
        args += ["--attach", f]
    if json_schema_file:
        args += ["--json-schema-file", json_schema_file]
    if max_budget_usd is not None:
        args += ["--max-budget-usd", str(max_budget_usd)]
    if tools:
        args += ["--tools", tools]
    if permission_mode:
        args += ["--permission-mode", permission_mode]
    if cwd:
        args += ["--cwd", cwd]
    args.append(prompt)

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"  # 確保跨平台 UTF-8
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise ClaudeCliError(proc.returncode, proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


if __name__ == "__main__":
    try:
        # 1) 單次呼叫
        r = call("用一句話說明什麼是 API。", max_budget_usd=0.10)
        print(f"[單次] {r['text']}  (花費 ${r['cost_usd']:.5f})")

        # 2) 多輪對話（session 延續）：第一輪 persist=True 存檔並拿 session_id，後續 resume
        a = call("記住：我的幸運數字是 7。只回覆 OK。", persist=True, max_budget_usd=0.10)
        b = call("我的幸運數字是多少？只回數字。", resume=a["session_id"], max_budget_usd=0.10)
        print(f"[延續] 回應：{b['text']}  (session={a['session_id'][:8]}…)")
    except ClaudeCliError as e:
        # 依結束碼決定要重試、還是叫使用者去設定環境
        print(e, file=sys.stderr)
        raise SystemExit(e.exit_code)
