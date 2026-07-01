# -*- coding: utf-8 -*-
"""
integration_sample.py
=====================
示範「另一支程式」如何呼叫本 CLI 拿到結果——**用 subprocess，不需要 import 本專案、
也不需要 pip install**。把這個 `call()` 函式複製到你的程式裡就能用。

要點：
  * 用 `--format json`：stdout 會是一個乾淨的 JSON 物件（答案 + session_id + 花費）。
  * 答案在 stdout、診斷在 stderr，所以直接 json.loads(stdout) 即可。
  * 結束碼：0 成功 / 1 呼叫失敗 / 2 找不到 claude / 3 未登入。

執行：  python integration_sample.py
"""

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


def call(
    prompt: str,
    *,
    model: str = "haiku",
    resume: str | None = None,
    persist: bool = False,
    attach: list[str] | None = None,
    json_schema_file: str | None = None,
    auth: str = "subscription",
    timeout: int = 180,
) -> dict:
    """呼叫本 CLI，回傳 dict：{text, structured_output, session_id, cost_usd, model, duration_ms}。

    多輪對話：第一輪帶 persist=True（才會存檔），拿回傳的 session_id；
              後續帶 resume=session_id 即可延續（Claude 記得前面說過的話）。
    attach：文字檔路徑清單，內容會被當輸入。
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
    args.append(prompt)

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"  # 確保跨平台 UTF-8
    proc = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", env=env, timeout=timeout
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"呼叫失敗 (exit {proc.returncode})：{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return json.loads(proc.stdout)


if __name__ == "__main__":
    # 1) 單次呼叫
    r = call("用一句話說明什麼是 API。")
    print(f"[單次] {r['text']}  (花費 ${r['cost_usd']:.5f})")

    # 2) 多輪對話（session 延續）：第一輪 persist=True 存檔並拿 session_id，後續 resume
    a = call("記住：我的幸運數字是 7。只回覆 OK。", persist=True)
    b = call("我的幸運數字是多少？只回數字。", resume=a["session_id"])
    print(f"[延續] 回應：{b['text']}  (session={a['session_id'][:8]}…)")
