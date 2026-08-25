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
* ``"subscription"``（預設）：強制走訂閱 OAuth。呼叫前會把 API key 類變數
  （``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN``）與第三方供應商導向變數
  （Bedrock / Vertex / Foundry / 自訂 ``ANTHROPIC_BASE_URL``）從子程序環境移除，
  確保真的走你的訂閱，不會被按量計費或雲端供應商靜默接走。
  （仍保留 ``CLAUDE_CODE_OAUTH_TOKEN``，這是 headless 用的訂閱 token。）
* ``"apikey"``：使用 ``ANTHROPIC_API_KEY``（按量計費，走 Commercial Terms）。
  此模式不會清掉 ``ANTHROPIC_BASE_URL`` 等變數，方便走自架 proxy / Bedrock / Vertex。
* ``"auto"``：照 Claude Code 既有的憑證優先順序，不做任何更動。

合規界線（重要，政策 2026 年數度變動）
--------------------------------------
* 允許：透過官方 ``claude`` 執行檔送出請求（本工具的做法）；或第三方工具自備 API key。
* 禁止：把訂閱 OAuth **token 抽出來自己直接打 Anthropic API**（OpenClaw / OpenCode
  之類的自製 harness）。
* 散佈給別人時：請對方在**自己的電腦**裝官方 Claude Code、用**自己的**帳號登入。
  **切勿散佈你自己的 token / 憑證**（違規且會算到你的額度）。大規模/商業散佈時，
  最無爭議的是讓每位使用者**自備 API key**（``--auth apikey``）。

計費提醒
--------
程式化呼叫會消耗你的訂閱額度（或 API 餘額）。省錢原則：
  * 預設用最便宜的模型（haiku），需要更高品質再切 sonnet / opus。
  * 預設關閉所有工具（``--tools ""``）→ 純文字進出，最便宜也最快，不會動你的檔案。
    打開工具會變成完整 agent，實測貴 15～45 倍。
  * 保留內建精簡系統提示（別用 Claude Code 預設那一大包）。
  * 用 ``max_budget_usd`` 設單次花費上限。
  * ``resume`` 每一輪都會重送完整對話歷史，成本隨輪數累加。

結束碼（CLI）
-------------
``0`` 成功｜``1`` 呼叫失敗｜``2`` 找不到 claude 執行檔｜``3`` 未登入 / 認證失敗｜
``4`` 參數或輸入檔錯誤。

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
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

__version__ = "0.2.0"

__all__ = [
    "ask",
    "check_setup",
    "find_claude_binary",
    "ClaudeResult",
    "ClaudeError",
    "ClaudeAuthError",
    "ClaudeNotFoundError",
    "EXIT_OK",
    "EXIT_CALL_FAILED",
    "EXIT_NO_BINARY",
    "EXIT_NOT_AUTHENTICATED",
    "EXIT_BAD_INPUT",
    "__version__",
]

# --------------------------------------------------------------------------- #
# 0. 結束碼契約（其他語言 shell out 時就是靠這幾個數字分辨失敗原因）
# --------------------------------------------------------------------------- #
EXIT_OK = 0  # 成功
EXIT_CALL_FAILED = 1  # 送出了但失敗（額度、逾時、模型錯誤、輸出無法解析…）
EXIT_NO_BINARY = 2  # 找不到 claude 執行檔（根本沒送出）
EXIT_NOT_AUTHENTICATED = 3  # 找得到執行檔，但沒登入 / 認證被拒
EXIT_BAD_INPUT = 4  # 呼叫端自己的問題：參數錯、附檔不存在、schema 檔壞掉


# --------------------------------------------------------------------------- #
# 1. 找到 claude 執行檔
# --------------------------------------------------------------------------- #
def _force_utf8_console() -> None:
    """把 stdout/stderr 逼成 UTF-8。

    Windows 主控台預設常是 cp950/cp936 等非 UTF-8 編碼，print ``✓``/``✗``
    這類符號會直接丟 UnicodeEncodeError（cp950 沒收錄這些 Unicode 符號）。
    在沒有設定 PYTHONUTF8=1 的情況下執行 ``--check`` 會整個中斷，所以在
    輸出任何東西前先 reconfigure；沒有 reconfigure（極舊版本/被重導向的
    非標準 stream）就直接放棄，不影響原本行為。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


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


def _home() -> Path:
    """取得使用者家目錄，取不到時回傳一個一定不存在的路徑。

    服務帳號、CI runner、精簡容器可能沒有設 HOME / USERPROFILE，這時
    ``Path.home()`` 會丟 ``RuntimeError``。那種情況應該讓「找不到 claude」的
    友善指引照常出現（家目錄下的候選路徑自然都不存在），而不是整個爆掉。
    """
    try:
        return Path.home()
    except RuntimeError:
        return Path(os.sep) / "__claude_subscription_no_home__"


def find_claude_binary() -> str:
    """回傳可用的 claude 執行檔路徑（跨平台）。

    搜尋順序：
      1. 環境變數 CLAUDE_BINARY（手動指定）
      2. PATH 上的 ``claude``（獨立安裝 CLI 最常見）
      3. 官方安裝器的預設位置（~/.local/bin 等）
      4. VSCode / Cursor / Windsurf 擴充內夾帶的 native-binary（挑版本號最高的）

    找不到時丟 ``ClaudeNotFoundError``（是 ``FileNotFoundError`` 的子類別，
    所以既有的 ``except FileNotFoundError`` 仍然接得到）。
    """
    is_win = platform.system() == "Windows"
    exe = "claude.exe" if is_win else "claude"
    home = _home()

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
            m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", p)
            return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)

        candidates.sort(key=version_key, reverse=True)
        return candidates[0]

    raise ClaudeNotFoundError(_install_hint())


def _resolve_binary(binary: Optional[str]) -> str:
    """把使用者給的 --binary / binary= 解析成真的存在的路徑。

    自己指定路徑時如果打錯，過去會等到 subprocess 才炸出 ``[WinError 2]``
    這種看不懂的訊息；這裡提前檢查並給出跟自動偵測失敗時一樣的安裝指引。
    """
    if not binary:
        return find_claude_binary()
    if Path(binary).exists():
        return binary
    found = shutil.which(binary)  # 允許只給名字（例如 "claude"）
    if found:
        return found
    raise ClaudeNotFoundError(f"指定的 claude 執行檔不存在：{binary}\n\n{_install_hint()}")


# --------------------------------------------------------------------------- #
# 2. 結果資料結構與例外
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
    """呼叫失敗時丟出。對應結束碼 1。"""


class ClaudeAuthError(ClaudeError):
    """認證失敗：沒登入、token 過期、API key 無效。對應結束碼 3。"""


class ClaudeNotFoundError(FileNotFoundError):
    """找不到 claude 執行檔。對應結束碼 2。

    繼承 FileNotFoundError 以維持與舊版程式碼的相容性。
    """


# 預設系統提示：把 Claude 框定成純資料處理，避免多餘輸出，也省 token。
_DEFAULT_SYSTEM = "你是一個精準的資料處理助手，只輸出被要求的內容，不要多餘解釋。"

# auth='subscription' 時要從子程序環境移除的變數。
# 前者會讓 Claude Code 改走按量計費的 API key；後者會把請求整個導去
# Bedrock / Vertex / Foundry / 自架 proxy——兩種都不是「用我的訂閱」。
_APIKEY_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_PROVIDER_ENV_VARS = (
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_BASE_URL",
    "ANTHROPIC_CUSTOM_HEADERS",
)

# 判斷失敗是不是「認證問題」的關鍵字（用來把結束碼從 1 升級成 3）。
# 這是啟發式判斷：claude 的錯誤訊息措辭可能改變，判斷不到時仍會回 1（呼叫失敗），
# 不會誤判成成功。
_AUTH_ERROR_MARKERS = (
    "invalid api key",
    "invalid bearer token",
    "authentication_error",
    "authentication failed",
    "unauthorized",
    "not logged in",
    "please log in",
    "login required",
    "oauth token has expired",
    "token expired",
    "expired credentials",
    "run `claude login`",
)


def _looks_like_auth_failure(*texts: str) -> bool:
    """從 stderr / stdout 判斷這次失敗是不是認證問題。"""
    blob = " ".join(t for t in texts if t).lower()
    return any(marker in blob for marker in _AUTH_ERROR_MARKERS)


def _read_attachments(paths: list) -> str:
    """把多個文字檔讀進來，包成帶檔名標頭的區塊字串。

    只支援文字檔（UTF-8，可含 BOM）。要讓 Claude 看圖片 / PDF 請改用
    ``tools="Read"`` 並在提示裡給**絕對路徑**，走官方 Read 工具。
    """
    blocks = []
    for p in paths:
        fp = Path(p)
        if not fp.exists():
            raise FileNotFoundError(f"附檔不存在：{fp}")
        try:
            content = fp.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as e:
            raise ValueError(
                f"附檔不是 UTF-8 文字檔：{fp}\n"
                "（--attach 只吃純文字。圖片 / PDF 請改用 --tools Read 並在提示裡給絕對路徑。）"
            ) from e
        blocks.append(f"===== 檔案：{fp.name} =====\n{content}\n===== 檔案結束：{fp.name} =====")
    return "\n\n".join(blocks)


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
    permission_mode: Optional[str] = None,
    timeout: int = 180,
    binary: Optional[str] = None,
    auth: str = "subscription",
    attach: Optional[list] = None,
    resume: Optional[str] = None,
    session_id: Optional[str] = None,
    persist: bool = False,
    cwd: Optional[str] = None,
    extra_args: Optional[list[str]] = None,
) -> ClaudeResult:
    """送一個提示給 Claude（透過官方 claude CLI），回傳 ClaudeResult。

    參數
    ----
    prompt        : 你的提示 / 要整理的資料（字串）。
    model         : 'haiku'(最便宜,預設) / 'sonnet'(均衡) / 'opus'(最強最貴) 或完整模型名。
    system        : 系統提示。設成 None 會用 Claude Code 預設（較貴）。
                    注意：覆寫系統提示會讓 Claude **不知道自己在哪個資料夾**，
                    所以搭配工具做檔案操作時，提示裡要給絕對路徑。
    json_schema   : 給定 JSON Schema 時，強制輸出符合該結構的 JSON（用 result.data 取得）。
    max_budget_usd: 單次呼叫花費上限（美金）。超過會中止，保護你的額度。
    tools         : 預設 "" 關閉所有工具（純文字進出，最便宜）。
                    "default" = 全開；或指定 "Read,Bash"。開了工具就是完整 agent，
                    實測成本是純文字的 15～45 倍。
    permission_mode: 工具的權限模式。只開 tools 而不設這個，寫檔類工具會被權限
                    機制擋下（headless 無法互動同意）。要真的能改檔案請設
                    'acceptEdits'。可用：acceptEdits / auto / bypassPermissions /
                    manual / dontAsk / plan。
    timeout       : 子程序逾時秒數。
    binary        : 自訂 claude 執行檔路徑（預設自動偵測）。
    auth          : 'subscription'(預設,走訂閱OAuth) / 'apikey'(用ANTHROPIC_API_KEY) /
                    'auto'(照 Claude Code 既有順序，不更動)。
    attach        : 要附帶的文字檔路徑清單；內容會以分隔標頭附在提示前面。
    resume        : 要延續的 session id（接續先前對話）。會自動開啟 session 保存。
                    注意每輪都會重送完整歷史，成本隨輪數累加。
    session_id    : 指定一個固定的 session id（UUID）來開新對話，方便日後 resume。
    persist       : True 時保留 session 到磁碟（resume/session_id 會自動視為 True）。
                    預設 False＝單次呼叫、用完即丟。
    cwd           : claude 子程序的工作目錄（預設＝呼叫端的目前目錄）。
                    **開啟工具時務必指定**，否則 Claude 會在呼叫你程式的那個
                    資料夾裡讀寫檔案。
    extra_args    : 額外要傳給 claude 的參數（list of str）。

    回傳的 ClaudeResult.session_id 可用於下一次 resume，達成多輪對話延續。

    例外
    ----
    ClaudeNotFoundError : 找不到 claude 執行檔（結束碼 2）。
    ClaudeAuthError     : 沒登入 / token 過期 / API key 無效（結束碼 3）。
    ClaudeError         : 其他呼叫失敗（結束碼 1）。
    FileNotFoundError   : 附檔不存在（結束碼 4）。
    ValueError          : auth 模式不合法、或附檔不是文字檔（結束碼 4）。
    """
    if auth not in ("subscription", "apikey", "auto"):
        raise ValueError(f"未知的 auth 模式：{auth!r}（可用：subscription / apikey / auto）")

    claude = _resolve_binary(binary)

    # 附檔：把每個檔案內容包進帶標頭的區塊，附在提示前面。
    if attach:
        prompt = _read_attachments(attach) + "\n" + prompt

    cmd: list[str] = [
        claude,
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--tools",
        tools,
    ]
    # session 延續：有 resume / session_id / persist 時才保留 session。
    want_persist = persist or bool(resume) or bool(session_id)
    if not want_persist:
        cmd.append("--no-session-persistence")
    if resume:
        cmd += ["--resume", resume]
    elif session_id:
        cmd += ["--session-id", session_id]
    # resume 時 session 已有系統提示，不再覆寫，避免衝突。
    if system is not None and not resume:
        cmd += ["--system-prompt", system]
    if json_schema is not None:
        cmd += ["--json-schema", json.dumps(json_schema, ensure_ascii=False)]
    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", str(max_budget_usd)]
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    if extra_args:
        cmd += extra_args

    # 依 auth 模式決定子程序的憑證環境。
    env = os.environ.copy()
    if auth == "subscription":
        # 強制走訂閱 OAuth：非互動模式下只要有 ANTHROPIC_API_KEY 就會優先被用
        # → 變成按量計費；而 Bedrock/Vertex/Foundry/自訂 base URL 則會把請求
        # 整個導去別的供應商。兩類都清掉，才是名副其實的「用我的訂閱」。
        # 保留 CLAUDE_CODE_OAUTH_TOKEN（headless 用的訂閱 token）。
        for var in _APIKEY_ENV_VARS + _PROVIDER_ENV_VARS:
            env.pop(var, None)
    elif auth == "apikey":
        if not env.get("ANTHROPIC_API_KEY"):
            raise ClaudeAuthError(
                "auth='apikey' 但環境中沒有 ANTHROPIC_API_KEY。請先設定該環境變數。"
            )
        # 不動 base URL 類變數：走自架 proxy / Bedrock / Vertex 是合理用法。
    # auth == "auto"：完全不更動，照 Claude Code 既有的憑證優先順序。

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # claude 若吐出非 UTF-8 位元組，不要蓋掉真正的錯誤原因
            env=env,
            cwd=cwd,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"呼叫逾時（{timeout}s）。") from e
    except OSError as e:  # 執行檔在解析後又消失、或路徑不可執行
        raise ClaudeNotFoundError(f"無法執行 {claude}：{e}\n\n{_install_hint()}") from e

    if proc.returncode != 0:
        detail = f"claude 子程序失敗 (exit {proc.returncode}).\nstderr:\n{proc.stderr.strip()}"
        if _looks_like_auth_failure(proc.stderr, proc.stdout):
            raise ClaudeAuthError(detail)
        raise ClaudeError(detail)

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeError(f"無法解析 claude 的 JSON 輸出。\nstdout:\n{proc.stdout[:2000]}") from e

    if payload.get("is_error") or payload.get("subtype") != "success":
        detail = (
            f"Claude 回報錯誤：subtype={payload.get('subtype')}, "
            f"api_error_status={payload.get('api_error_status')}\n{proc.stdout[:1000]}"
        )
        # 401/403 是明確的認證失敗；其餘再用關鍵字啟發式判斷。
        if payload.get("api_error_status") in (401, 403) or _looks_like_auth_failure(
            proc.stdout, proc.stderr
        ):
            raise ClaudeAuthError(detail)
        raise ClaudeError(detail)

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
    """檢查本機環境並印出指引；回傳 0 代表可用，非 0 是上面定義的結束碼。"""
    _force_utf8_console()
    print(f"=== Claude 訂閱工具 v{__version__} — 環境檢查 ===")
    print(f"OS: {platform.system()} / Python {platform.python_version()}")

    if auth not in ("subscription", "apikey", "auto"):
        print(f"✗ 未知的 auth 模式：{auth!r}（可用：subscription / apikey / auto）")
        return EXIT_BAD_INPUT

    # 1) 找執行檔
    try:
        binary = find_claude_binary()
    except ClaudeNotFoundError as e:
        print("✗ 找不到 claude 執行檔。\n")
        print(e)
        return EXIT_NO_BINARY
    print(f"✓ 找到 claude： {binary}")

    # 2) 偵測登入狀態（只是線索，不是判決——macOS 的憑證可能存在 Keychain 裡）
    creds = _home() / ".claude" / ".credentials.json"
    has_creds = creds.exists()
    has_oauth_env = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"  訂閱憑證檔（{creds.name}）：{'有' if has_creds else '無'}")
    print(f"  CLAUDE_CODE_OAUTH_TOKEN 環境變數：{'有' if has_oauth_env else '無'}")
    print(f"  ANTHROPIC_API_KEY 環境變數：{'有' if has_api_key else '無'}")

    redirected = [v for v in _PROVIDER_ENV_VARS if os.environ.get(v)]
    if redirected:
        note = "（auth=subscription 會自動清掉它們）" if auth == "subscription" else "（會生效）"
        print(f"  ⚠ 偵測到第三方供應商設定：{', '.join(redirected)} {note}")

    if auth == "apikey" and not has_api_key:
        print("\n✗ auth=apikey 但未設定 ANTHROPIC_API_KEY。")
        return EXIT_NOT_AUTHENTICATED

    no_subscription_signal = auth == "subscription" and not (has_creds or has_oauth_env)
    if no_subscription_signal:
        print("\n⚠ 沒看到訂閱憑證檔或 OAuth token 環境變數。")
        print("    互動登入：    執行 `claude`，依瀏覽器提示登入 Claude.ai 帳號")
        print("    無瀏覽器登入： 執行 `claude setup-token`，把輸出設為 CLAUDE_CODE_OAUTH_TOKEN")
        if platform.system() == "Darwin":
            print("    （macOS 也可能把憑證存在 Keychain，所以這裡顯示「無」不一定代表沒登入。）")

    # 3) 實測 ping —— 這才是唯一有決定性的檢查
    if not do_ping:
        if no_subscription_signal:
            print("\n✗ 未偵測到登入憑證（已略過實測，加上實測才能確定）。")
            return EXIT_NOT_AUTHENTICATED
        print("\n✓ 靜態檢查通過（已用 --no-ping 略過實測呼叫）。")
        return EXIT_OK

    print(f"\n用 auth='{auth}' 實測呼叫中（haiku，花費極小）…")
    try:
        r = ask(
            "Reply with exactly: OK",
            model="haiku",
            auth=auth,
            max_budget_usd=0.10,
            timeout=60,
        )
    except ClaudeAuthError as e:
        print(f"✗ 認證失敗：{e}")
        return EXIT_NOT_AUTHENTICATED
    except ClaudeNotFoundError as e:
        print(f"✗ 找不到執行檔：{e}")
        return EXIT_NO_BINARY
    except ValueError as e:
        print(f"✗ 參數錯誤：{e}")
        return EXIT_BAD_INPUT
    except ClaudeError as e:
        print(f"✗ 呼叫失敗：{e}")
        return EXIT_CALL_FAILED

    ok = "OK" in r.text
    print(f"{'✓' if ok else '✗'} 回應：{r.text.strip()!r}｜花費 ${r.cost_usd:.5f}")
    if not ok:
        return EXIT_CALL_FAILED

    print("\n✓ 一切就緒，可以使用了。")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# 5. 命令列介面（讓任何語言都能 shell out 呼叫）
# --------------------------------------------------------------------------- #
class _ArgParser(argparse.ArgumentParser):
    """argparse 預設用結束碼 2 表示「參數錯誤」，會跟本工具的「找不到執行檔」撞號。

    這裡改成 EXIT_BAD_INPUT(4)，讓結束碼契約一致。
    """

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"{self.prog}: 錯誤：{message}", file=sys.stderr)
        raise SystemExit(EXIT_BAD_INPUT)


def _build_parser() -> _ArgParser:
    parser = _ArgParser(
        prog="claude-sub",
        description="用 Claude Code 訂閱方案呼叫 Claude（非按量 API）。",
        epilog=(
            "結束碼：0 成功｜1 呼叫失敗｜2 找不到 claude 執行檔｜"
            "3 未登入/認證失敗｜4 參數或輸入檔錯誤"
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"claude-subscription {__version__}"
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="提示文字；省略時改從 --prompt-file 或 stdin 讀取。"
        "（提示若以 - 開頭，前面加 -- 分隔。）",
    )
    parser.add_argument(
        "--prompt-file",
        help="從檔案讀取提示（UTF-8，可含 BOM）。Windows 上傳中文最穩定的方式。",
    )
    parser.add_argument(
        "--attach",
        action="append",
        default=[],
        metavar="FILE",
        help="附帶一個文字檔當輸入內容（可重複多次帶多個檔）。只吃純文字檔。",
    )
    parser.add_argument("--model", default="haiku", help="haiku(預設)/sonnet/opus 或完整模型名")
    parser.add_argument("--system", default=None, help="系統提示（覆寫內建預設）")
    parser.add_argument(
        "--no-system", action="store_true", help="使用 Claude Code 預設系統提示（較貴）"
    )
    parser.add_argument("--json-schema-file", help="JSON Schema 檔路徑，強制結構化輸出")
    parser.add_argument("--max-budget-usd", type=float, default=None, help="單次花費上限(USD)")
    parser.add_argument("--timeout", type=int, default=180, help="逾時秒數")
    parser.add_argument("--binary", default=None, help="自訂 claude 執行檔路徑")
    parser.add_argument(
        "--auth",
        choices=("subscription", "apikey", "auto"),
        default="subscription",
        help="登入方式：subscription(預設) / apikey / auto",
    )
    # ── agent 模式（預設完全關閉：純文字進出，最便宜也不會動你的檔案）──
    agent = parser.add_argument_group(
        "agent 模式",
        "打開工具後就是完整 agent（能讀寫檔案、執行指令、看圖片）。"
        "實測成本是純文字模式的 15～45 倍，請搭配 --max-budget-usd 使用。",
    )
    agent.add_argument(
        "--tools", default="", help='工具集，預設 "" 全關；"default" 全開；或 "Read,Bash"'
    )
    agent.add_argument(
        "--permission-mode",
        choices=("acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"),
        default=None,
        help="工具權限模式。只開 --tools 而不設這個，寫檔會被權限機制擋下"
        "（headless 無法互動同意）。要真的能改檔案請用 acceptEdits。",
    )
    agent.add_argument(
        "--cwd",
        metavar="DIR",
        default=None,
        help="claude 的工作目錄（預設＝目前目錄）。開工具時強烈建議指定，"
        "否則它會在呼叫你程式的資料夾裡讀寫檔案。",
    )
    agent.add_argument(
        "--claude-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="直接透傳一個參數給官方 claude（可重複）。"
        "例：--claude-arg --add-dir --claude-arg /data",
    )
    # ── session 延續（三者互斥）──
    session = parser.add_mutually_exclusive_group()
    session.add_argument("--resume", metavar="SESSION_ID", help="延續指定 session id 的對話")
    session.add_argument(
        "--continue",
        dest="continue_last",
        action="store_true",
        help="延續這個資料夾最近一次對話（等同 claude --continue）",
    )
    session.add_argument(
        "--session", metavar="UUID", help="指定固定 session id 開新對話，方便日後 --resume"
    )
    parser.add_argument(
        "--persist", action="store_true", help="保留 session 到磁碟（單次預設不保留）"
    )
    # ── 輸出 ──
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="text(預設,只印答案) / json(印含 session_id、cost 的完整物件，方便程式接)",
    )
    parser.add_argument(
        "--output-file",
        metavar="FILE",
        help="把 stdout 的內容另存到檔案（UTF-8）。搭配 --format json 時存的是整個 JSON 物件。",
    )
    parser.add_argument("--show-cost", action="store_true", help="在 stderr 印出本次花費")
    parser.add_argument(
        "--which", action="store_true", help="只印出偵測到的 claude 執行檔路徑後結束"
    )
    parser.add_argument(
        "--check", action="store_true", help="檢查本機環境與登入狀態（新電腦先跑這個）"
    )
    parser.add_argument(
        "--no-ping",
        action="store_true",
        help="搭配 --check：只做靜態檢查，不實際送出呼叫（不花錢，適合 CI）",
    )
    return parser


_PASSTHROUGH_FLAG = "--claude-arg"


def _normalize_passthrough(argv: list[str]) -> list[str]:
    """把 ``--claude-arg --add-dir`` 改寫成 ``--claude-arg=--add-dir``。

    argparse 只要看到選項的值以 ``-`` 開頭，就會當成另一個旗標而報「expected one
    argument」——但要透傳給 claude 的參數幾乎一定以 ``-`` 開頭，等於這個功能不能用。
    先合併成 ``=`` 形式，argparse 才收得下（``=`` 後面的東西一律當值）。

    遇到裸的 ``--`` 之後就停止改寫，讓使用者仍能用 ``--`` 分隔以 ``-`` 開頭的提示。
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--":  # 之後都是位置參數，原封不動
            out.extend(argv[i:])
            break
        if token == _PASSTHROUGH_FLAG and i + 1 < len(argv):
            out.append(f"{_PASSTHROUGH_FLAG}={argv[i + 1]}")
            i += 2
            continue
        out.append(token)
        i += 1
    return out


def _read_prompt(args: argparse.Namespace, parser: _ArgParser) -> str:
    """依序從位置參數 / --prompt-file / stdin 取得提示。"""
    if args.prompt is not None:
        return args.prompt
    if args.prompt_file:
        path = Path(args.prompt_file)
        if not path.exists():
            parser.error(f"--prompt-file 不存在：{path}")
        return path.read_text(encoding="utf-8-sig")
    # stdin：如果是互動終端機就不要傻等（過去會靜默卡死，看起來像當機）。
    stdin = sys.stdin
    if stdin is None or stdin.isatty():
        parser.error(
            '沒有提供提示。請用位置參數、--prompt-file，或從管線餵 stdin。'
            '（例：claude-sub "你的提示"）'
        )
    raw = stdin.buffer.read()
    # 從原始位元組以 UTF-8 解碼（best-effort）。
    # 注意：PowerShell 5.1 用管線 | 餵非 ASCII 文字會先損毀資料，
    # 中文請改用 --prompt-file 或位置參數，最可靠。
    return raw.decode("utf-8", errors="replace")


def _main(argv: Optional[list[str]] = None) -> int:
    _force_utf8_console()
    parser = _build_parser()
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    args = parser.parse_args(_normalize_passthrough(raw_argv))

    if args.which:
        try:
            print(find_claude_binary())
            return EXIT_OK
        except ClaudeNotFoundError as e:
            print(e, file=sys.stderr)
            return EXIT_NO_BINARY

    if args.check:
        return check_setup(auth=args.auth, do_ping=not args.no_ping)

    prompt = _read_prompt(args, parser)
    if not prompt.strip():
        parser.error("提示是空的（參數、--prompt-file、stdin 皆為空）。")

    schema = None
    if args.json_schema_file:
        schema_path = Path(args.json_schema_file)
        if not schema_path.exists():
            parser.error(f"--json-schema-file 不存在：{schema_path}")
        try:
            # utf-8-sig 可同時容忍有/無 BOM 的檔（Windows 編輯器常加 BOM）
            schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            parser.error(f"--json-schema-file 不是合法的 JSON：{schema_path}（{e}）")

    if args.cwd and not Path(args.cwd).is_dir():
        parser.error(f"--cwd 不是資料夾：{args.cwd}")

    # 延續對話時，session 已有系統提示，不再覆寫。
    continuing = bool(args.resume) or args.continue_last
    if continuing:
        system_arg: Any = None
    elif args.system is not None:
        system_arg = args.system
    elif args.no_system:
        system_arg = None
    else:
        system_arg = _DEFAULT_SYSTEM

    # --continue 沒有對應的 ask() 參數，透過透傳送給 claude，並需保留 session。
    extra = list(args.claude_arg)
    if args.continue_last:
        extra.append("--continue")

    try:
        result = ask(
            prompt,
            model=args.model,
            system=system_arg,
            json_schema=schema,
            max_budget_usd=args.max_budget_usd,
            tools=args.tools,
            permission_mode=args.permission_mode,
            timeout=args.timeout,
            binary=args.binary,
            auth=args.auth,
            attach=args.attach,
            resume=args.resume,
            session_id=args.session,
            persist=args.persist or args.continue_last,
            cwd=args.cwd,
            extra_args=extra or None,
        )
    except ClaudeNotFoundError as e:  # 必須排在 FileNotFoundError 之前
        print(f"[claude_subscription] 錯誤：{e}", file=sys.stderr)
        return EXIT_NO_BINARY
    except ClaudeAuthError as e:  # 必須排在 ClaudeError 之前
        print(f"[claude_subscription] 認證錯誤：{e}", file=sys.stderr)
        return EXIT_NOT_AUTHENTICATED
    except ClaudeError as e:
        print(f"[claude_subscription] 錯誤：{e}", file=sys.stderr)
        return EXIT_CALL_FAILED
    except (FileNotFoundError, ValueError) as e:  # 附檔不存在 / 附檔非文字 / auth 值錯
        print(f"[claude_subscription] 輸入錯誤：{e}", file=sys.stderr)
        return EXIT_BAD_INPUT

    # 決定要輸出的內容。
    if args.format == "json":
        # 完整物件，方便程式接（含 session_id 供延續對話用）。
        out = json.dumps(
            {
                "text": result.text,
                "structured_output": result.structured_output,
                "session_id": result.session_id,
                "cost_usd": result.cost_usd,
                "model": args.model,
                "duration_ms": result.duration_ms,
            },
            ensure_ascii=False,
            indent=2,
        )
    elif result.structured_output is not None:
        # 有用 json_schema 時，輸出結構化 JSON 而非口語確認句。
        out = json.dumps(result.structured_output, ensure_ascii=False, indent=2)
    else:
        out = result.text

    # 存檔（可選）。
    if args.output_file:
        Path(args.output_file).write_text(out, encoding="utf-8")

    # 結果到 stdout（純淨，方便 pipe）。
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")

    # 診斷資訊一律到 stderr（不污染 stdout）。
    if args.show_cost or args.persist or args.session or continuing:
        msg = (
            f"[claude_subscription] 花費 ${result.cost_usd:.6f}｜模型 {args.model}"
            f"｜{result.duration_ms} ms"
        )
        if result.session_id:
            msg += f"｜session={result.session_id}"
        print(msg, file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(_main())
