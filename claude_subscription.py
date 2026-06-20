"""
claude_subscription.py
======================

在程式裡呼叫 Claude，**透過官方 Claude Code 執行檔**（``claude -p`` headless 模式），
可使用「Claude 訂閱方案（Pro / Max OAuth 登入）」或「API key」。零第三方相依套件。

原理
----
本工具不自己打 Anthropic API、也不碰你的 token，而是把**官方 ``claude`` 執行檔**
當子程序呼叫。請求一律「經過官方 Claude Code」送出，所以用的就是你本機 Claude Code
所設定的登入方式。每個使用者在自己的電腦上用自己的帳號登入即可。

登入方式（auth 參數 / --auth）
------------------------------
* ``"subscription"``（預設）：強制走訂閱 OAuth。呼叫前會把 ``ANTHROPIC_API_KEY`` /
  ``ANTHROPIC_AUTH_TOKEN`` 從子程序環境移除，避免被按量計費搶走。
  （仍保留 ``CLAUDE_CODE_OAUTH_TOKEN``，這是 headless 用的訂閱 token。）
* ``"apikey"``：使用 ``ANTHROPIC_API_KEY``（按量計費，走 Commercial Terms）。
* ``"auto"``：照 Claude Code 既有的憑證優先順序，不做任何更動。

合規界線（重要，政策 2026 年數度變動）
--------------------------------------
* ✅ 允許：透過官方 ``claude`` 執行檔送出請求（本工具的做法）；或第三方工具自備 API key。
* ❌ 禁止：把訂閱 OAuth **token 抽出來自己直接打 Anthropic API**（OpenClaw / OpenCode
  之類的自製 harness）。
* 散佈給別人時：請對方在**自己的電腦**裝官方 Claude Code、用**自己的**帳號登入。
  **切勿散佈你自己的 token / 憑證**（違規且會算到你的額度）。大規模/商業散佈時，
  最無爭議的是讓每位使用者**自備 API key**（``--auth apikey``）。

計費提醒
--------
程式化呼叫會消耗你的訂閱額度（或 API 餘額）。省錢原則：
  * 預設用最便宜的模型（haiku），需要更高品質再切 sonnet / opus。
  * 預設關閉所有工具（``--tools ""``）→ 純文字進出，最便宜也最快，不會動你的檔案。
  * 保留內建精簡系統提示（別用 Claude Code 預設那一大包）。
  * 用 ``max_budget_usd`` 設單次花費上限。

使用方式
--------
1. Python 程式內：``from claude_subscription import ask``
2. 任何語言（shell out）：``python claude_subscription.py --model haiku "你的提示"``
3. 新電腦先自我診斷：``python claude_subscription.py --check``
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# 1. 找到 claude 執行檔
# --------------------------------------------------------------------------- #
def _install_hint() -> str:
    """依作業系統回傳安裝 / 登入指引。"""
    if platform.system() == "Windows":
        install = (
            "  安裝（PowerShell）： irm https://claude.ai/install.ps1 | iex\n"
            "  或裝 VSCode 擴充「Anthropic.claude-code」"
        )
    else:
        install = "  安裝： curl -fsSL https://claude.ai/install.sh | bash"
    return (
        "找不到 claude 執行檔。請先安裝官方 Claude Code，並用你自己的帳號登入：\n"
        f"{install}\n"
        "  登入（互動）： 執行 `claude` 會開瀏覽器登入 Claude.ai 帳號\n"
        "  登入（無瀏覽器/伺服器）： `claude setup-token` 取得 token，"
        "再設環境變數 CLAUDE_CODE_OAUTH_TOKEN\n"
        "  已安裝但偵測不到： 設環境變數 CLAUDE_BINARY 指向 claude(.exe) 的完整路徑"
    )


def find_claude_binary() -> str:
    """回傳可用的 claude 執行檔路徑（跨平台）。

    搜尋順序：
      1. 環境變數 CLAUDE_BINARY（手動指定）
      2. PATH 上的 ``claude``（獨立安裝 CLI 最常見）
      3. 官方安裝器的預設位置（~/.local/bin 等）
      4. VSCode / Cursor / Windsurf 擴充內夾帶的 native-binary（挑版本號最高的）
    """
    is_win = platform.system() == "Windows"
    exe = "claude.exe" if is_win else "claude"
    home = Path.home()

    # 1) 手動指定
    override = os.environ.get("CLAUDE_BINARY")
    if override and Path(override).exists():
        return override

    # 2) PATH
    on_path = shutil.which("claude")
    if on_path:
        return on_path

    # 3) 官方安裝器常見位置
    common = [
        home / ".local" / "bin" / exe,
        home / ".claude" / "local" / exe,
    ]
    if is_win:
        common += [
            home / "AppData" / "Local" / "Programs" / "claude" / exe,
            home / "AppData" / "Roaming" / "npm" / "claude.cmd",
        ]
    else:
        common += [Path("/usr/local/bin") / exe, Path("/opt/homebrew/bin") / exe]
    for c in common:
        if c.exists():
            return str(c)

    # 4) 編輯器擴充內的 native-binary（各平台資料夾後綴不同，用 * 萬用）
    candidates: list[str] = []
    for variant in (".vscode", ".vscode-insiders", ".cursor", ".windsurf"):
        candidates += glob.glob(
            str(
                home
                / variant
                / "extensions"
                / "anthropic.claude-code-*"
                / "resources"
                / "native-binary"
                / exe
            )
        )

    if candidates:
        # 依資料夾中的版本號 (x.y.z) 由高到低排序，取最新
        def version_key(p: str) -> tuple:
            import re

            m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", p)
            return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)

        candidates.sort(key=version_key, reverse=True)
        return candidates[0]

    raise FileNotFoundError(_install_hint())


# --------------------------------------------------------------------------- #
# 2. 結果資料結構
# --------------------------------------------------------------------------- #
@dataclass
class ClaudeResult:
    """一次呼叫的結果。"""

    text: str  # Claude 回傳的文字（result 欄位）
    cost_usd: float  # 本次花費（會從你的每月額度扣）
    structured_output: Any = None  # 用 json_schema 時的結構化結果（已是 Python 物件）
    model_usage: dict = field(default_factory=dict)  # 各模型 token 用量
    num_turns: int = 0
    duration_ms: int = 0
    session_id: str = ""
    raw: dict = field(default_factory=dict)  # 完整原始 JSON

    @property
    def data(self) -> Any:
        """取得結構化資料（Python 物件）。

        * 若呼叫時帶了 json_schema → 直接回傳 structured_output。
        * 否則嘗試把 text 當 JSON 解析（解析失敗會丟 ValueError）。
        """
        if self.structured_output is not None:
            return self.structured_output
        return json.loads(self.text)


class ClaudeError(RuntimeError):
    """呼叫失敗時丟出。"""


# 預設系統提示：把 Claude 框定成純資料處理，避免多餘輸出，也省 token。
_DEFAULT_SYSTEM = "你是一個精準的資料處理助手，只輸出被要求的內容，不要多餘解釋。"


# --------------------------------------------------------------------------- #
# 3. 核心呼叫函式
# --------------------------------------------------------------------------- #
def ask(
    prompt: str,
    *,
    model: str = "haiku",
    system: Optional[str] = _DEFAULT_SYSTEM,
    json_schema: Optional[dict] = None,
    max_budget_usd: Optional[float] = None,
    tools: str = "",  # "" = 關掉所有工具（純文字進出）; "default" = 全開; 或 "Read,Bash"
    timeout: int = 180,
    binary: Optional[str] = None,
    auth: str = "subscription",
    extra_args: Optional[list[str]] = None,
) -> ClaudeResult:
    """送一個提示給 Claude（透過官方 claude CLI），回傳 ClaudeResult。

    參數
    ----
    prompt        : 你的提示 / 要整理的資料（字串）。
    model         : 'haiku'(最便宜,預設) / 'sonnet'(均衡) / 'opus'(最強最貴) 或完整模型名。
    system        : 系統提示。設成 None 會用 Claude Code 預設（較貴，不建議）。
    json_schema   : 給定 JSON Schema 時，強制輸出符合該結構的 JSON（用 result.data 取得）。
    max_budget_usd: 單次呼叫花費上限（美金）。超過會中止，保護你的額度。
    tools         : 預設 "" 關閉所有工具。要讓 Claude 讀檔/執行指令才改。
    timeout       : 子程序逾時秒數。
    binary        : 自訂 claude 執行檔路徑（預設自動偵測）。
    auth          : 'subscription'(預設,走訂閱OAuth) / 'apikey'(用ANTHROPIC_API_KEY) /
                    'auto'(照 Claude Code 既有順序，不更動)。
    extra_args    : 額外要傳給 claude 的參數（list of str）。

    例外
    ----
    ClaudeError       : Claude 回報錯誤、子程序失敗、或 auth='apikey' 卻沒有 API key。
    FileNotFoundError : 找不到 claude 執行檔。
    ValueError        : auth 模式不合法。
    """
    claude = binary or find_claude_binary()

    cmd: list[str] = [
        claude,
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--tools",
        tools,
        "--no-session-persistence",
    ]
    if system is not None:
        cmd += ["--system-prompt", system]
    if json_schema is not None:
        cmd += ["--json-schema", json.dumps(json_schema, ensure_ascii=False)]
    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", str(max_budget_usd)]
    if extra_args:
        cmd += extra_args

    # 依 auth 模式決定子程序的憑證環境。
    env = os.environ.copy()
    if auth == "subscription":
        # 強制走訂閱 OAuth：移除 API key 類變數（非互動模式下只要有
        # ANTHROPIC_API_KEY 就會優先被用 → 變成按量計費）。
        # 保留 CLAUDE_CODE_OAUTH_TOKEN（headless 用的訂閱 token）。
        for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(var, None)
    elif auth == "apikey":
        if not env.get("ANTHROPIC_API_KEY"):
            raise ClaudeError(
                "auth='apikey' 但環境中沒有 ANTHROPIC_API_KEY。請先設定該環境變數。"
            )
    elif auth == "auto":
        pass  # 不更動，照 Claude Code 既有的憑證優先順序
    else:
        raise ValueError(f"未知的 auth 模式：{auth!r}（可用：subscription / apikey / auto）")

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"呼叫逾時（{timeout}s）。") from e

    if proc.returncode != 0:
        raise ClaudeError(
            f"claude 子程序失敗 (exit {proc.returncode}).\nstderr:\n{proc.stderr.strip()}"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeError(
            f"無法解析 claude 的 JSON 輸出。\nstdout:\n{proc.stdout[:2000]}"
        ) from e

    if payload.get("is_error") or payload.get("subtype") != "success":
        raise ClaudeError(
            f"Claude 回報錯誤：subtype={payload.get('subtype')}, "
            f"api_error_status={payload.get('api_error_status')}\n{proc.stdout[:1000]}"
        )

    return ClaudeResult(
        text=payload.get("result", ""),
        cost_usd=float(payload.get("total_cost_usd", 0.0)),
        structured_output=payload.get("structured_output"),
        model_usage=payload.get("modelUsage", {}),
        num_turns=int(payload.get("num_turns", 0)),
        duration_ms=int(payload.get("duration_ms", 0)),
        session_id=payload.get("session_id", ""),
        raw=payload,
    )


# --------------------------------------------------------------------------- #
# 4. 自我診斷（新電腦上先跑這個）
# --------------------------------------------------------------------------- #
def check_setup(auth: str = "subscription", do_ping: bool = True) -> int:
    """檢查本機環境並印出指引；回傳 0 代表可用、非 0 代表需處理。"""
    print("=== Claude 訂閱工具 — 環境檢查 ===")
    print(f"OS: {platform.system()} / Python {platform.python_version()}")

    # 1) 找執行檔
    try:
        binary = find_claude_binary()
    except FileNotFoundError as e:
        print("✗ 找不到 claude 執行檔。\n")
        print(e)
        return 2
    print(f"✓ 找到 claude： {binary}")

    # 2) 偵測登入狀態
    creds = Path.home() / ".claude" / ".credentials.json"
    has_creds = creds.exists()
    has_oauth_env = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"  訂閱憑證檔（{creds.name}）：{'有' if has_creds else '無'}")
    print(f"  CLAUDE_CODE_OAUTH_TOKEN 環境變數：{'有' if has_oauth_env else '無'}")
    print(f"  ANTHROPIC_API_KEY 環境變數：{'有' if has_api_key else '無'}")

    if auth == "subscription" and not (has_creds or has_oauth_env):
        print("\n✗ 尚未登入訂閱。請二擇一：")
        print("    互動登入：    執行 `claude`，依瀏覽器提示登入 Claude.ai 帳號")
        print("    無瀏覽器登入： 執行 `claude setup-token`，把輸出設為 CLAUDE_CODE_OAUTH_TOKEN")
        return 3
    if auth == "apikey" and not has_api_key:
        print("\n✗ auth=apikey 但未設定 ANTHROPIC_API_KEY。")
        return 3

    # 3) 實測 ping
    if do_ping:
        print(f"\n用 auth='{auth}' 實測呼叫中（haiku，花費極小）…")
        try:
            r = ask(
                "Reply with exactly: OK",
                model="haiku",
                auth=auth,
                max_budget_usd=0.10,
                timeout=60,
            )
        except (ClaudeError, ValueError) as e:
            print(f"✗ 呼叫失敗：{e}")
            return 4
        ok = "OK" in r.text
        print(f"{'✓' if ok else '✗'} 回應：{r.text.strip()!r}｜花費 ${r.cost_usd:.5f}")
        if not ok:
            return 4

    print("\n✓ 一切就緒，可以使用了。")
    return 0


# --------------------------------------------------------------------------- #
# 5. 命令列介面（讓任何語言都能 shell out 呼叫）
# --------------------------------------------------------------------------- #
def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="用 Claude Code 訂閱方案呼叫 Claude（非按量 API）。"
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="提示文字；省略時改從 --prompt-file 或 stdin 讀取。",
    )
    parser.add_argument(
        "--prompt-file",
        help="從檔案讀取提示（UTF-8，可含 BOM）。Windows 上傳中文最穩定的方式。",
    )
    parser.add_argument("--model", default="haiku", help="haiku(預設)/sonnet/opus 或完整模型名")
    parser.add_argument("--system", default=None, help="系統提示（覆寫內建預設）")
    parser.add_argument("--no-system", action="store_true", help="使用 Claude Code 預設系統提示（較貴）")
    parser.add_argument("--json-schema-file", help="JSON Schema 檔路徑，強制結構化輸出")
    parser.add_argument("--max-budget-usd", type=float, default=None, help="單次花費上限(USD)")
    parser.add_argument("--tools", default="", help='工具集，預設 "" 全關；"default" 全開')
    parser.add_argument("--timeout", type=int, default=180, help="逾時秒數")
    parser.add_argument("--binary", default=None, help="自訂 claude 執行檔路徑")
    parser.add_argument(
        "--auth",
        choices=("subscription", "apikey", "auto"),
        default="subscription",
        help="登入方式：subscription(預設) / apikey / auto",
    )
    parser.add_argument("--show-cost", action="store_true", help="在 stderr 印出本次花費")
    parser.add_argument(
        "--which", action="store_true", help="只印出偵測到的 claude 執行檔路徑後結束"
    )
    parser.add_argument(
        "--check", action="store_true", help="檢查本機環境與登入狀態（新電腦先跑這個）"
    )
    args = parser.parse_args(argv)

    if args.which:
        try:
            print(find_claude_binary())
            return 0
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            return 2

    if args.check:
        return check_setup(auth=args.auth)

    if args.prompt is not None:
        prompt = args.prompt
    elif args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8-sig")
    else:
        # 從 stdin 讀原始位元組再以 UTF-8 解碼（best-effort）。
        # 注意：PowerShell 5.1 用管線 | 餵非 ASCII 文字會先損毀資料，
        # 中文請改用 --prompt-file 或 --prompt 參數，最可靠。
        raw = sys.stdin.buffer.read()
        prompt = raw.decode("utf-8", errors="replace")
    if not prompt.strip():
        parser.error("沒有提供提示（參數、--prompt-file、stdin 皆為空）。")

    schema = None
    if args.json_schema_file:
        # utf-8-sig 可同時容忍有/無 BOM 的檔（Windows 編輯器常加 BOM）
        schema = json.loads(Path(args.json_schema_file).read_text(encoding="utf-8-sig"))

    # --system 優先；否則 --no-system 用內建預設(None)；否則用 ask() 的預設值
    if args.system is not None:
        system_arg: Any = args.system
    elif args.no_system:
        system_arg = None
    else:
        system_arg = _DEFAULT_SYSTEM

    try:
        result = ask(
            prompt,
            model=args.model,
            system=system_arg,
            json_schema=schema,
            max_budget_usd=args.max_budget_usd,
            tools=args.tools,
            timeout=args.timeout,
            binary=args.binary,
            auth=args.auth,
        )
    except (ClaudeError, FileNotFoundError, ValueError) as e:
        print(f"[claude_subscription] 錯誤：{e}", file=sys.stderr)
        return 1

    # 結果到 stdout（純淨，方便 pipe）；花費到 stderr。
    # 有用 json_schema 時，輸出結構化 JSON 而非口語確認句。
    if result.structured_output is not None:
        out = json.dumps(result.structured_output, ensure_ascii=False, indent=2)
    else:
        out = result.text
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    if args.show_cost:
        print(
            f"[claude_subscription] 本次花費 ${result.cost_usd:.6f}｜模型 {args.model}"
            f"｜{result.duration_ms} ms（從你的每月 Agent SDK 額度扣）",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
