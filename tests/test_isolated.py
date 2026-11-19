# -*- coding: utf-8 -*-
"""
tests/test_isolated.py
======================
隔離模式（``isolated=True``）與 ``search()`` 的離線測試。

全程用假的子程序（mock 掉 ``subprocess.run`` / ``subprocess.Popen`` 與 ``claude --help``），
**不會真的呼叫 Claude、不連網、不開任何埠**。驗的是「組出來的參數、環境變數、工作目錄」。

執行：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import claude_subscription as cs  # noqa: E402

_ = cs.platform.system()        # 暖 platform 的快取（見 test_claude_subscription.py）
_ = tempfile.gettempdir()       # 暖 tempfile 的快取：下面會把 os.environ 換成假的

FAKE_BINARY = "/fake/path/to/claude"

# 假的 claude --help：列出隔離模式會用到的所有旗標。
FAKE_HELP = "\n".join([
    "Usage: claude [options] [command] [prompt]",
    "  -p, --print  Print response and exit",
    "  --output-format <format>",
    "  --model <model>",
    "  --tools <tools...>",
    "  --allowedTools, --allowed-tools <tools...>",
    "  --disallowedTools, --disallowed-tools <tools...>",
    '  --permission-mode <mode>  (choices: "acceptEdits", "auto", "dontAsk", "plan")',
    "  --no-session-persistence",
    "  --system-prompt <prompt>",
    "  --system-prompt-snapshot <on|off>",
    "  --json-schema <schema>",
    "  --max-budget-usd <amount>",
    "  --setting-sources <sources>",
    "  --safe-mode",
    "  --restricted",
    "  --strict-mcp-config",
    "  --mcp-config <configs...>",
    "  --disable-slash-commands",
    "  --no-chrome",
    "  --verbose",
    "  --include-partial-messages",
])

# 假的使用者環境：有該留的，也有一堆不該傳給子程序的金鑰。
FAKE_ENV = {
    "PATH": "/usr/bin",
    "HOME": "/home/someone",
    "USERPROFILE": "/home/someone",
    "SYSTEMROOT": "C:/Windows",
    "LANG": "en_US.UTF-8",
    "HTTPS_PROXY": "http://proxy.example:3128",
    "CLAUDE_CODE_OAUTH_TOKEN": "fake-oauth-token",
    "ANTHROPIC_API_KEY": "fake-api-key",
    "ANTHROPIC_AUTH_TOKEN": "fake-auth-token",
    "ANTHROPIC_BASE_URL": "https://gateway.example",
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "OPENAI_API_KEY": "fake-openai",
    "GITHUB_TOKEN": "fake-github",
    "AWS_SECRET_ACCESS_KEY": "fake-aws",
    "SOME_APP_PASSWORD": "fake-password",
    "TEMP": "/tmp/original",
    "TMP": "/tmp/original",
}
SECRET_KEYS = ("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "OPENAI_API_KEY", "GITHUB_TOKEN",
               "AWS_SECRET_ACCESS_KEY", "SOME_APP_PASSWORD")

ISOLATION_FLAGS = ("--safe-mode", "--restricted", "--strict-mcp-config", "--disable-slash-commands",
                   "--no-chrome", "--no-session-persistence")


def make_payload(**overrides) -> dict:
    payload = {
        "subtype": "success",
        "is_error": False,
        "result": "OK",
        "total_cost_usd": 0.001,
        "session_id": "s-iso",
        "num_turns": 1,
        "duration_ms": 10,
        "modelUsage": {},
    }
    payload.update(overrides)
    return payload


def completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def iso_dirs() -> set:
    return set(Path(tempfile.gettempdir()).glob("claude-iso-*"))


class FakeRun:
    """假的 subprocess.run：記下每次呼叫，並在「呼叫當下」記錄工作目錄的狀態。"""

    def __init__(self, stdout=None, returncode=0, stderr=""):
        self.calls = []
        self.stdout = json.dumps(make_payload()) if stdout is None else stdout
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, cmd, **kwargs):
        cwd = kwargs.get("cwd")
        snapshot = {
            "cmd": list(cmd),
            "kwargs": kwargs,
            "cwd_exists": bool(cwd) and os.path.isdir(cwd),
            "cwd_listing": os.listdir(cwd) if cwd and os.path.isdir(cwd) else None,
            "tmp_exists": os.path.isdir(kwargs["env"]["TEMP"]) if "TEMP" in (kwargs.get("env") or {}) else None,
        }
        self.calls.append(snapshot)
        return completed(self.stdout, self.stderr, self.returncode)


class IsoCase(unittest.TestCase):
    """換掉執行檔偵測、claude --help 與 os.environ，讓測試完全不碰本機的 Claude Code。"""

    help_text = FAKE_HELP

    def setUp(self):
        # 每個測試自己一個暫存根目錄：隔離模式開的資料夾都落在這裡，好檢查、也不掃整個系統暫存區。
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        for patcher in (
            mock.patch.object(tempfile, "tempdir", root.name),
            mock.patch.object(cs, "find_claude_binary", return_value=FAKE_BINARY),
            mock.patch.object(cs, "_claude_help", side_effect=lambda *a, **k: self.help_text),
            mock.patch.dict(os.environ, FAKE_ENV, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_ask(self, fake=None, **kwargs):
        fake = fake or FakeRun()
        with mock.patch.object(cs.subprocess, "run", side_effect=fake):
            result = cs.ask("秘密查詢 canary-query-42", **kwargs)
        return result, fake.calls[-1]


# --------------------------------------------------------------------------- #
# 1. 預設行為不變
# --------------------------------------------------------------------------- #
class TestDefaultUnchanged(IsoCase):
    def test_default_is_not_isolated(self):
        _r, call = self.run_ask()
        cmd = call["cmd"]
        for flag in ("--safe-mode", "--restricted", "--strict-mcp-config", "--setting-sources"):
            self.assertNotIn(flag, cmd)
        self.assertIsNone(call["kwargs"]["cwd"])
        # 預設仍是整份環境（只清掉 API key／供應商變數）
        self.assertEqual(call["kwargs"]["env"]["GITHUB_TOKEN"], "fake-github")

    def test_default_never_reads_help(self):
        with mock.patch.object(cs, "_claude_help") as help_:
            self.run_ask()
        help_.assert_not_called()


# --------------------------------------------------------------------------- #
# 2. 隔離模式的參數
# --------------------------------------------------------------------------- #
class TestIsolatedArgv(IsoCase):
    def test_no_settings_no_memory_no_mcp_no_session(self):
        _r, call = self.run_ask(isolated=True)
        cmd = call["cmd"]
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "")  # 不讀 user/project/local
        for flag in ISOLATION_FLAGS:
            self.assertIn(flag, cmd)
        self.assertNotIn("--mcp-config", cmd)          # 沒給任何 MCP 設定 + strict = 零個 MCP
        for flag in ("--resume", "--session-id", "--continue", "--add-dir", "--dangerously-skip-permissions"):
            self.assertNotIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "dontAsk")

    def test_default_isolated_has_no_tools_at_all(self):
        _r, call = self.run_ask(isolated=True)
        cmd = call["cmd"]
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertNotIn("--allowedTools", cmd)
        self.assertEqual(cmd[cmd.index("--disallowedTools") + 1], "WebFetch")

    def test_websearch_only(self):
        _r, call = self.run_ask(isolated=True, tools="WebSearch")
        cmd = call["cmd"]
        self.assertEqual(cmd[cmd.index("--tools") + 1], "WebSearch")
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "WebSearch")
        self.assertEqual(cmd[cmd.index("--disallowedTools") + 1], "WebFetch")
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "dontAsk")
        self.assertNotIn("WebFetch", cmd[cmd.index("--allowedTools") + 1])

    def test_explicit_dontask_is_accepted(self):
        _r, call = self.run_ask(isolated=True, tools="WebSearch", permission_mode="dontAsk")
        self.assertEqual(call["cmd"].count("--permission-mode"), 1)

    def test_query_goes_to_stdin_not_argv_or_env(self):
        _r, call = self.run_ask(isolated=True)
        self.assertIn("canary-query-42", call["kwargs"]["input"])
        self.assertFalse(any("canary-query-42" in part for part in call["cmd"]))
        self.assertFalse(any("canary-query-42" in v for v in call["kwargs"]["env"].values()))

    def test_system_prompt_and_budget_still_work(self):
        _r, call = self.run_ask(isolated=True, system="S", max_budget_usd=0.05)
        cmd = call["cmd"]
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], "S")
        self.assertEqual(cmd[cmd.index("--max-budget-usd") + 1], "0.05")


# --------------------------------------------------------------------------- #
# 3. 環境變數白名單
# --------------------------------------------------------------------------- #
class TestIsolatedEnv(IsoCase):
    def test_subscription_env_is_whitelisted(self):
        _r, call = self.run_ask(isolated=True)
        env = call["kwargs"]["env"]
        for key in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "LANG", "HTTPS_PROXY"):
            self.assertEqual(env[key], FAKE_ENV[key])
        self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "fake-oauth-token")
        for key in SECRET_KEYS + ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
            self.assertNotIn(key, env)
        self.assertEqual(env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "1")
        self.assertEqual(env["ENABLE_CLAUDEAI_MCP_SERVERS"], "false")
        self.assertEqual(env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"], "1")

    def test_only_expected_keys(self):
        _r, call = self.run_ask(isolated=True)
        allowed = {"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "LANG", "HTTPS_PROXY",
                   "CLAUDE_CODE_OAUTH_TOKEN", "TEMP", "TMP", "TMPDIR",
                   "CLAUDE_CODE_DISABLE_AUTO_MEMORY", "ENABLE_CLAUDEAI_MCP_SERVERS",
                   "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"}
        self.assertEqual(set(call["kwargs"]["env"]), allowed)

    def test_apikey_env_keeps_only_the_key(self):
        _r, call = self.run_ask(isolated=True, auth="apikey")
        env = call["kwargs"]["env"]
        self.assertEqual(env["ANTHROPIC_API_KEY"], "fake-api-key")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://gateway.example")
        for key in SECRET_KEYS + ("CLAUDE_CODE_OAUTH_TOKEN",):
            self.assertNotIn(key, env)

    def test_temp_vars_point_into_the_throwaway_folder(self):
        _r, call = self.run_ask(isolated=True)
        env = call["kwargs"]["env"]
        self.assertTrue(call["tmp_exists"])
        self.assertEqual(env["TEMP"], env["TMP"])
        self.assertEqual(env["TEMP"], env["TMPDIR"])
        self.assertEqual(Path(env["TEMP"]).parent, Path(call["kwargs"]["cwd"]).parent)
        self.assertNotEqual(env["TEMP"], FAKE_ENV["TEMP"])

    def test_auth_auto_is_rejected(self):
        with mock.patch.object(cs.subprocess, "run") as run, self.assertRaises(ValueError):
            cs.ask("q", isolated=True, auth="auto")
        run.assert_not_called()

    def test_apikey_without_key_is_auth_error(self):
        os.environ.pop("ANTHROPIC_API_KEY")
        with mock.patch.object(cs.subprocess, "run") as run, self.assertRaises(cs.ClaudeAuthError):
            cs.ask("q", isolated=True, auth="apikey")
        run.assert_not_called()


# --------------------------------------------------------------------------- #
# 4. 工作目錄：新開、空的、用完刪掉
# --------------------------------------------------------------------------- #
class TestIsolatedWorkdir(IsoCase):
    def test_fresh_empty_dir_removed_afterwards(self):
        before = iso_dirs()
        _r, call = self.run_ask(isolated=True)
        cwd = call["kwargs"]["cwd"]
        self.assertTrue(call["cwd_exists"])
        self.assertEqual(call["cwd_listing"], [])
        self.assertTrue(Path(cwd).parent.name.startswith("claude-iso-"))
        self.assertFalse(os.path.exists(cwd))
        self.assertFalse(os.path.exists(Path(cwd).parent))
        self.assertEqual(iso_dirs(), before)

    def test_each_call_gets_its_own_dir(self):
        _r, first = self.run_ask(isolated=True)
        _r, second = self.run_ask(isolated=True)
        self.assertNotEqual(first["kwargs"]["cwd"], second["kwargs"]["cwd"])

    def test_removed_even_when_the_call_fails(self):
        before = iso_dirs()
        fake = FakeRun(stdout="", returncode=1, stderr="boom")
        with self.assertRaises(cs.ClaudeError):
            self.run_ask(fake, isolated=True)
        self.assertFalse(os.path.exists(fake.calls[-1]["kwargs"]["cwd"]))
        self.assertEqual(iso_dirs(), before)

    def test_files_left_by_claude_are_removed_too(self):
        def run(cmd, **kwargs):
            Path(kwargs["cwd"], "leftover.txt").write_text("x", encoding="utf-8")
            Path(kwargs["env"]["TEMP"], "cache.bin").write_bytes(b"x")
            run.cwd = kwargs["cwd"]
            return completed(json.dumps(make_payload()))

        with mock.patch.object(cs.subprocess, "run", side_effect=run):
            cs.ask("q", isolated=True)
        self.assertFalse(os.path.exists(Path(run.cwd).parent))


# --------------------------------------------------------------------------- #
# 5. 不能跟會削弱隔離的參數一起用
# --------------------------------------------------------------------------- #
class TestIsolatedConflicts(IsoCase):
    BAD = (
        {"cwd": "."},
        {"resume": "s-0"},
        {"session_id": "11111111-1111-1111-1111-111111111111"},
        {"persist": True},
        {"extra_args": ["--add-dir", "/data"]},
        {"tools": "Read"},
        {"tools": "default"},
        {"tools": "WebSearch,WebFetch"},
        {"tools": "WebFetch"},
        {"permission_mode": "acceptEdits"},
        {"permission_mode": "bypassPermissions"},
    )

    def test_conflicts_raise_before_anything_runs(self):
        before = iso_dirs()
        for kwargs in self.BAD:
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}):
                with mock.patch.object(cs.subprocess, "run") as run, \
                        mock.patch.object(cs.subprocess, "Popen") as popen:
                    with self.assertRaises(ValueError):
                        cs.ask("q", isolated=True, **kwargs)
                    with self.assertRaises(ValueError):
                        cs.ask_stream("q", lambda e: None, isolated=True, **kwargs)
                run.assert_not_called()
                popen.assert_not_called()
        self.assertEqual(iso_dirs(), before)


# --------------------------------------------------------------------------- #
# 6. 版本不支援就明確報錯，不放寬
# --------------------------------------------------------------------------- #
class TestUnsupportedVersion(IsoCase):
    def _expect_unsupported(self, missing_flag, **kwargs):
        self.help_text = FAKE_HELP.replace(missing_flag, "--something-else")
        with mock.patch.object(cs.subprocess, "run") as run:
            with self.assertRaises(cs.ClaudeIsolationUnsupportedError) as ctx:
                cs.ask("q", isolated=True, **kwargs)
        run.assert_not_called()
        return ctx.exception

    def test_each_isolation_flag_is_required(self):
        for flag in ("--safe-mode", "--restricted", "--setting-sources", "--strict-mcp-config",
                     "--disable-slash-commands", "--no-session-persistence", "--no-chrome",
                     "--disallowedTools"):
            with self.subTest(flag=flag):
                err = self._expect_unsupported(flag)
                self.assertIn(flag, err.missing)
                self.assertIn(flag, str(err))

    def test_allowed_tools_required_for_websearch(self):
        err = self._expect_unsupported("--allowedTools", tools="WebSearch")
        self.assertIn("--allowedTools", err.missing)

    def test_dontask_mode_required(self):
        err = self._expect_unsupported('"dontAsk"')
        self.assertIn("dontAsk", err.missing)

    def test_flag_prefix_does_not_count(self):
        """--system-prompt-snapshot 存在不代表 --system-prompt 存在。"""
        self.help_text = FAKE_HELP.replace("--system-prompt <prompt>", "")
        with mock.patch.object(cs.subprocess, "run"), \
                self.assertRaises(cs.ClaudeIsolationUnsupportedError) as ctx:
            cs.ask("q", isolated=True)
        self.assertEqual(ctx.exception.missing, ["--system-prompt"])

    def test_is_a_claude_error_and_cleans_up(self):
        before = iso_dirs()
        err = self._expect_unsupported("--safe-mode")
        self.assertIsInstance(err, cs.ClaudeError)
        self.assertEqual(iso_dirs(), before)

    def test_cli_exit_code_is_call_failed(self):
        self.help_text = FAKE_HELP.replace("--safe-mode", "")
        with mock.patch.object(cs.subprocess, "run"), redirect_stderr(io.StringIO()) as err, \
                redirect_stdout(io.StringIO()):
            code = cs._main(["--isolated", "q"])
        self.assertEqual(code, cs.EXIT_CALL_FAILED)
        self.assertIn("--safe-mode", err.getvalue())


class TestClaudeHelpReader(unittest.TestCase):
    """_claude_help 本身：用假的 subprocess.run 驗證讀說明的方式與失敗處理。"""

    def setUp(self):
        cs._HELP_CACHE.clear()
        self.addCleanup(cs._HELP_CACHE.clear)

    def test_reads_help_with_given_env_and_cwd(self):
        with mock.patch.object(cs.subprocess, "run", return_value=completed(FAKE_HELP)) as run:
            text = cs._claude_help(FAKE_BINARY, {"PATH": "x"}, "/somewhere")
        self.assertIn("--safe-mode", text)
        self.assertEqual(run.call_args.args[0], [FAKE_BINARY, "--help"])
        self.assertEqual(run.call_args.kwargs["env"], {"PATH": "x"})
        self.assertEqual(run.call_args.kwargs["cwd"], "/somewhere")

    def test_failures_are_unsupported_not_silent(self):
        cases = (
            {"side_effect": OSError("gone")},
            {"side_effect": subprocess.TimeoutExpired(cmd="claude", timeout=30)},
            {"return_value": completed("", "boom", 1)},
            {"return_value": completed("garbage")},
        )
        for case in cases:
            with self.subTest(case=str(case)):
                with mock.patch.object(cs.subprocess, "run", **case), \
                        self.assertRaises(cs.ClaudeIsolationUnsupportedError):
                    cs._claude_help(FAKE_BINARY, {}, ".")

    def test_cached_per_binary_version(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "claude")
            Path(exe).write_text("v1", encoding="utf-8")
            with mock.patch.object(cs.subprocess, "run", return_value=completed(FAKE_HELP)) as run:
                cs._claude_help(exe, {}, d)
                cs._claude_help(exe, {}, d)
                self.assertEqual(run.call_count, 1)
                Path(exe).write_text("v2 is longer", encoding="utf-8")   # 換版本 → 重查
                cs._claude_help(exe, {}, d)
                self.assertEqual(run.call_count, 2)

    def test_full_isolated_call_reads_help_in_the_isolated_env(self):
        calls = []

        def run(cmd, **kwargs):
            calls.append((list(cmd), kwargs))
            if cmd[-1] == "--help":
                return completed(FAKE_HELP)
            return completed(json.dumps(make_payload()))

        with mock.patch.object(cs, "find_claude_binary", return_value=FAKE_BINARY), \
                mock.patch.dict(os.environ, FAKE_ENV, clear=True), \
                mock.patch.object(cs.subprocess, "run", side_effect=run):
            cs.ask("q", isolated=True)
        self.assertEqual([c[0][-1] == "--help" for c in calls], [True, False])
        help_kwargs, real_kwargs = calls[0][1], calls[1][1]
        self.assertNotIn("GITHUB_TOKEN", help_kwargs["env"])
        self.assertEqual(help_kwargs["cwd"], real_kwargs["cwd"])


# --------------------------------------------------------------------------- #
# 7. 不把查詢寫進日誌／錯誤訊息
# --------------------------------------------------------------------------- #
class TestNoQueryLeak(IsoCase):
    def test_success_prints_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.run_ask(isolated=True)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

    def test_error_result_does_not_echo_stdout(self):
        payload = make_payload(subtype="error_during_execution", is_error=True, result="",
                               echoed="canary-query-42")
        fake = FakeRun(stdout=json.dumps(payload))
        with self.assertRaises(cs.ClaudeError) as ctx:
            self.run_ask(fake, isolated=True)
        self.assertNotIn("canary-query-42", str(ctx.exception))

    def test_unparsable_output_does_not_echo_stdout(self):
        fake = FakeRun(stdout="not json canary-query-42")
        with self.assertRaises(cs.ClaudeError) as ctx:
            self.run_ask(fake, isolated=True)
        self.assertNotIn("canary-query-42", str(ctx.exception))

    def test_non_isolated_errors_unchanged(self):
        fake = FakeRun(stdout="not json canary-query-42")
        with self.assertRaises(cs.ClaudeError) as ctx:
            self.run_ask(fake)
        self.assertIn("canary-query-42", str(ctx.exception))


# --------------------------------------------------------------------------- #
# 8. ask_stream 與 search()
# --------------------------------------------------------------------------- #
class FakePopen:
    """假的 claude 子程序。pid 預設 None：測試永遠不會拿假的 pid 去叫真的 taskkill。"""

    instances: list = []

    def __init__(self, cmd, lines=(), returncode=0, err_text="", pid=None, **kwargs):
        self.cmd = list(cmd)
        self.kwargs = kwargs
        cwd = kwargs.get("cwd")
        self.cwd_listing = os.listdir(cwd) if cwd and os.path.isdir(cwd) else None
        self.stdin = io.StringIO()
        self.stdin.close = lambda: None
        self._lines = [line + "\n" for line in lines]
        self.returncode = None
        self._rc = returncode
        self.stderr = io.StringIO(err_text)
        self.pid = pid
        self.killed = False
        FakePopen.instances.append(self)

    @property
    def stdout(self):
        yield from self._lines

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = -9 if self.killed else self._rc
        return self.returncode

    def kill(self):
        self.killed = True


SEARCH_LINKS = json.dumps([
    {"title": "Python 3.13 release notes", "url": "https://docs.python.org/3/whatsnew/3.13.html"},
    {"title": "Python downloads", "url": "https://www.python.org/downloads/"},
])


def search_stream(answer: str, links: str = SEARCH_LINKS) -> list:
    return [
        json.dumps({"type": "system", "subtype": "init", "tools": ["WebSearch"]}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "WebSearch", "input": {"query": "python latest"}}]}}),
        json.dumps({"type": "user", "message": {"content": [{
            "type": "tool_result", "tool_use_id": "t1",
            "content": f'Web search results for query: "python latest"\n\nLinks: {links}\n\nsummary'}]}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": answer}]}}),
        json.dumps(make_payload(type="result", result=answer)),
    ]


class StreamCase(IsoCase):
    def run_search(self, answer, links=SEARCH_LINKS, **kwargs):
        FakePopen.instances = []
        lines = search_stream(answer, links)
        factory = lambda cmd, **kw: FakePopen(cmd, lines, **kw)  # noqa: E731
        with mock.patch.object(cs.subprocess, "Popen", side_effect=factory):
            out = cs.search("最新的 Python 版本？", **kwargs)
        return out, FakePopen.instances[-1]


class TestIsolatedStream(StreamCase):
    def test_ask_stream_isolated(self):
        FakePopen.instances = []
        factory = lambda cmd, **kw: FakePopen(cmd, search_stream("ok"), **kw)  # noqa: E731
        with mock.patch.object(cs.subprocess, "Popen", side_effect=factory):
            cs.ask_stream("q", lambda e: None, isolated=True, tools="WebSearch")
        proc = FakePopen.instances[-1]
        for flag in ISOLATION_FLAGS + ("--verbose",):
            self.assertIn(flag, proc.cmd)
        self.assertEqual(proc.cwd_listing, [])
        self.assertNotIn("GITHUB_TOKEN", proc.kwargs["env"])
        self.assertFalse(os.path.exists(proc.kwargs["cwd"]))


class TestSearch(StreamCase):
    def test_shape_and_isolated_argv(self):
        answer = ("Python 3.13 是目前最新版。\n\n來源：\n"
                  "- [Python 3.13 release notes](https://docs.python.org/3/whatsnew/3.13.html)")
        out, proc = self.run_search(answer)
        self.assertEqual(set(out), {"text", "sources"})
        self.assertEqual(out["text"], answer)
        self.assertEqual(out["sources"], [
            {"title": "Python 3.13 release notes", "url": "https://docs.python.org/3/whatsnew/3.13.html"}])
        cmd = proc.cmd
        self.assertEqual(cmd[cmd.index("--tools") + 1], "WebSearch")
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "WebSearch")
        self.assertEqual(cmd[cmd.index("--disallowedTools") + 1], "WebFetch")
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "dontAsk")
        for flag in ISOLATION_FLAGS:
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], cs._SEARCH_SYSTEM)
        self.assertEqual(proc.stdin.getvalue(), "最新的 Python 版本？")
        self.assertFalse(os.path.exists(proc.kwargs["cwd"]))

    def test_hallucinated_links_are_dropped(self):
        answer = ("見 [官方](https://www.python.org/downloads/) 與 "
                  "[不存在](https://made-up.example/page)。")
        out, _ = self.run_search(answer)
        self.assertEqual([s["url"] for s in out["sources"]], ["https://www.python.org/downloads/"])

    def test_no_citations_falls_back_to_search_results(self):
        out, _ = self.run_search("Python 3.13。")
        self.assertEqual([s["url"] for s in out["sources"]], [
            "https://docs.python.org/3/whatsnew/3.13.html", "https://www.python.org/downloads/"])
        self.assertEqual(out["sources"][0]["title"], "Python 3.13 release notes")

    def test_unknown_result_format_gives_no_sources(self):
        """（待擁有者確認的語意）讀不到搜尋結果時回空清單，不回答案裡未驗證的網址。"""
        out, _ = self.run_search("見 https://example.org/a.", links="(no links)")
        self.assertEqual(out["sources"], [])

    def test_bare_url_matches_hit_with_trailing_slash_difference(self):
        out, _ = self.run_search("見 https://www.python.org/downloads 。")
        self.assertEqual(out["sources"], [{"title": "Python downloads",
                                           "url": "https://www.python.org/downloads"}])

    def test_on_event_passthrough(self):
        seen = []
        self.run_search("x", on_event=seen.append)
        self.assertEqual(seen[-1]["type"], "result")

    def test_empty_query_rejected(self):
        with mock.patch.object(cs.subprocess, "Popen") as popen:
            for bad in ("", "   ", None):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    cs.search(bad)
        popen.assert_not_called()

    def test_non_isolated_search_keeps_websearch_only(self):
        out, proc = self.run_search("x", isolated=False)
        cmd = proc.cmd
        self.assertNotIn("--safe-mode", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "WebSearch")
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "WebSearch")
        self.assertEqual(cmd[cmd.index("--disallowedTools") + 1], "WebFetch")
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "dontAsk")
        self.assertIsNone(proc.kwargs["cwd"])

    def test_unsupported_version_surfaces_from_search(self):
        self.help_text = FAKE_HELP.replace("--restricted", "")
        with mock.patch.object(cs.subprocess, "Popen") as popen, \
                self.assertRaises(cs.ClaudeIsolationUnsupportedError):
            cs.search("q")
        popen.assert_not_called()


# --------------------------------------------------------------------------- #
# 9. CLI
# --------------------------------------------------------------------------- #
class TestCliIsolated(IsoCase):
    def test_flag_passes_isolated(self):
        with mock.patch.object(cs, "ask", return_value=cs.ClaudeResult(text="ok", cost_usd=0)) as ask, \
                redirect_stdout(io.StringIO()):
            code = cs._main(["--isolated", "--tools", "WebSearch", "q"])
        self.assertEqual(code, cs.EXIT_OK)
        self.assertTrue(ask.call_args.kwargs["isolated"])

    def test_default_cli_not_isolated(self):
        with mock.patch.object(cs, "ask", return_value=cs.ClaudeResult(text="ok", cost_usd=0)) as ask, \
                redirect_stdout(io.StringIO()):
            cs._main(["q"])
        self.assertFalse(ask.call_args.kwargs["isolated"])

    def test_conflicting_cli_flags_are_bad_input(self):
        with tempfile.TemporaryDirectory() as d:
            for argv in (["--isolated", "--cwd", d, "q"], ["--isolated", "--persist", "q"],
                         ["--isolated", "--continue", "q"], ["--isolated", "--tools", "Read", "q"],
                         ["--isolated", "--claude-arg=--add-dir", "q"]):
                with self.subTest(argv=argv), mock.patch.object(cs.subprocess, "run") as run, \
                        redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                    self.assertEqual(cs._main(argv), cs.EXIT_BAD_INPUT)
                    run.assert_not_called()


# --------------------------------------------------------------------------- #
# 10. 裁判審查後補的測試（每一條先在修正前的程式上失敗過）
# --------------------------------------------------------------------------- #
class TestStreamKillsChildOnAbort(IsoCase):
    """讀取途中被中斷（Ctrl+C、on_event 丟 BaseException）時，子程序要被殺掉，暫存資料夾也要刪掉。"""

    def _abort(self, platform_name, pid):
        FakePopen.instances = []
        factory = lambda cmd, **kw: FakePopen(cmd, search_stream("ok"), pid=pid, **kw)  # noqa: E731

        def interrupt(_event):
            raise KeyboardInterrupt

        with mock.patch.object(cs.sys, "platform", platform_name), \
                mock.patch.object(cs.subprocess, "Popen", side_effect=factory), \
                mock.patch.object(cs.subprocess, "run") as run:
            with self.assertRaises(KeyboardInterrupt):
                cs.ask_stream("q", interrupt, isolated=True, tools="WebSearch")
        return FakePopen.instances[-1], run

    def test_child_killed_and_dir_removed_when_interrupted(self):
        before = iso_dirs()
        proc, run = self._abort("linux", pid=None)
        self.assertTrue(proc.killed)
        run.assert_not_called()                         # 非 Windows 不叫 taskkill
        self.assertFalse(os.path.exists(proc.kwargs["cwd"]))
        self.assertEqual(iso_dirs(), before)

    def test_windows_kills_the_whole_tree(self):
        """npm 的 claude.cmd 是 cmd.exe 包著 node：只殺 cmd.exe 的話 node 會留下來。"""
        proc, run = self._abort("win32", pid=4242)
        self.assertTrue(proc.killed)
        self.assertEqual(run.call_args.args[0], ["taskkill", "/T", "/F", "/PID", "4242"])

    def test_finished_child_is_not_killed(self):
        FakePopen.instances = []
        factory = lambda cmd, **kw: FakePopen(cmd, search_stream("ok"), pid=4242, **kw)  # noqa: E731
        with mock.patch.object(cs.sys, "platform", "win32"), \
                mock.patch.object(cs.subprocess, "Popen", side_effect=factory), \
                mock.patch.object(cs.subprocess, "run") as run:
            cs.ask_stream("q", lambda e: None, isolated=True, tools="WebSearch")
        self.assertFalse(FakePopen.instances[-1].killed)
        run.assert_not_called()


class TestIsolatedErrorsAreRedacted(IsoCase):
    """隔離模式的錯誤訊息只說結束碼與錯誤類別，不附 claude 的 stderr／result 原文。"""

    CANARY = "canary-query-42"

    def _stream(self, lines=(), returncode=0, err_text=""):
        factory = lambda cmd, **kw: FakePopen(cmd, lines, returncode, err_text, **kw)  # noqa: E731
        with mock.patch.object(cs.subprocess, "Popen", side_effect=factory):
            cs.ask_stream("q", lambda e: None, isolated=True)

    def test_process_failure_stderr_not_in_message(self):
        fake = FakeRun(stdout="", returncode=1, stderr=f"Error: something about {self.CANARY}")
        with self.assertRaises(cs.ClaudeError) as ctx:
            self.run_ask(fake, isolated=True)
        self.assertNotIn(self.CANARY, str(ctx.exception))
        self.assertIn("exit 1", str(ctx.exception))
        self.assertFalse(os.path.exists(fake.calls[-1]["kwargs"]["cwd"]))

    def test_stream_process_failure_stderr_not_in_message(self):
        with self.assertRaises(cs.ClaudeError) as ctx:
            self._stream(returncode=2, err_text=f"crash {self.CANARY}")
        self.assertNotIn(self.CANARY, str(ctx.exception))

    def test_auth_failure_still_classified_but_redacted(self):
        fake = FakeRun(stdout="", returncode=1, stderr=f"Please log in again {self.CANARY}")
        with self.assertRaises(cs.ClaudeAuthError) as ctx:
            self.run_ask(fake, isolated=True)
        self.assertNotIn(self.CANARY, str(ctx.exception))

    def test_usage_limit_still_classified_but_redacted(self):
        fake = FakeRun(stdout="", returncode=1, stderr=f"You've hit your limit {self.CANARY} · resets 7pm")
        with self.assertRaises(cs.ClaudeUsageLimitError) as ctx:
            self.run_ask(fake, isolated=True)
        self.assertNotIn(self.CANARY, str(ctx.exception))
        self.assertEqual(ctx.exception.resets, "7pm")

    def test_error_result_text_not_in_message(self):
        payload = make_payload(subtype="success", is_error=True, api_error_status=500,
                               result=f"API Error: model said {self.CANARY}")
        with self.assertRaises(cs.ClaudeError) as ctx:
            self.run_ask(FakeRun(stdout=json.dumps(payload)), isolated=True)
        self.assertNotIn(self.CANARY, str(ctx.exception))
        self.assertIn("500", str(ctx.exception))

    def test_stream_error_result_text_not_in_message(self):
        bad = json.dumps(make_payload(type="result", subtype="error_during_execution", is_error=True,
                                      result=f"partial answer {self.CANARY}"))
        with self.assertRaises(cs.ClaudeError) as ctx:
            self._stream(lines=[bad])
        self.assertNotIn(self.CANARY, str(ctx.exception))

    def test_non_isolated_failure_still_shows_stderr(self):
        fake = FakeRun(stdout="", returncode=1, stderr=f"boom {self.CANARY}")
        with self.assertRaises(cs.ClaudeError) as ctx:
            self.run_ask(fake)
        self.assertIn(self.CANARY, str(ctx.exception))


class TestFlagDetectionUsesDeclarations(IsoCase):
    """旗標只算「選項宣告」那一行；只在別的旗標的說明裡被提到不算。"""

    def _expect_missing(self, missing):
        with mock.patch.object(cs.subprocess, "run") as run, \
                self.assertRaises(cs.ClaudeIsolationUnsupportedError) as ctx:
            cs.ask("q", isolated=True)
        run.assert_not_called()
        self.assertEqual(ctx.exception.missing, missing)

    def test_flag_only_mentioned_in_another_description(self):
        self.help_text = FAKE_HELP.replace(
            "  --safe-mode\n", "").replace("  --restricted", "  --restricted  stricter than --safe-mode")
        self._expect_missing(["--safe-mode"])

    def test_dontask_only_mentioned_elsewhere(self):
        self.help_text = FAKE_HELP.replace(', "dontAsk"', "").replace(
            "  --no-chrome", "  --no-chrome  (unrelated: dontAsk)")
        self._expect_missing(["dontAsk"])

    def test_wrapped_description_still_counts(self):
        self.help_text = FAKE_HELP.replace(
            '  --permission-mode <mode>  (choices: "acceptEdits", "auto", "dontAsk", "plan")',
            '  --permission-mode <mode>  Permission mode (choices: "acceptEdits",\n'
            '                            "auto", "dontAsk", "plan")')
        _r, call = self.run_ask(isolated=True)
        self.assertIn("--safe-mode", call["cmd"])

    def test_alias_on_the_same_declaration_counts(self):
        _r, call = self.run_ask(isolated=True, tools="WebSearch")   # --allowedTools, --allowed-tools
        self.assertIn("--allowedTools", call["cmd"])


class TestIsolatedRejectsDashValues(IsoCase):
    """隔離模式不讓 model／system 的值長得像旗標（怕被 claude 當成另一個旗標）。"""

    def test_dash_values_rejected_before_running(self):
        for kwargs in ({"model": "--dangerously-skip-permissions"}, {"model": "-x"},
                       {"system": "--add-dir=/"}, {"system": "- rule one"}):
            with self.subTest(**kwargs), mock.patch.object(cs.subprocess, "run") as run, \
                    mock.patch.object(cs.subprocess, "Popen") as popen:
                with self.assertRaises(ValueError):
                    cs.ask("q", isolated=True, **kwargs)
                with self.assertRaises(ValueError):
                    cs.ask_stream("q", lambda e: None, isolated=True, **kwargs)
                run.assert_not_called()
                popen.assert_not_called()

    def test_normal_values_and_default_mode_unaffected(self):
        _r, call = self.run_ask(isolated=True, model="claude-haiku-4-5", system="\n- rule one")
        self.assertEqual(call["cmd"][call["cmd"].index("--model") + 1], "claude-haiku-4-5")
        _r, call = self.run_ask(system="- rule one")                 # 非隔離：照舊
        self.assertEqual(call["cmd"][call["cmd"].index("--system-prompt") + 1], "- rule one")


WIKI_URL = "https://en.wikipedia.org/wiki/Python_(programming_language)"
WIKI_LINKS = json.dumps([{"title": "Python (programming language)", "url": WIKI_URL},
                         {"title": "Python downloads", "url": "https://www.python.org/downloads/"}])


def stream_without_search(answer: str) -> list:
    """模型根本沒搜尋（沒有 user 事件），直接回答。"""
    return [
        json.dumps({"type": "system", "subtype": "init", "tools": ["WebSearch"]}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": answer}]}}),
        json.dumps(make_payload(type="result", result=answer)),
    ]


class TestSourcesReview(StreamCase):
    def test_markdown_link_with_parentheses(self):
        out, _ = self.run_search(f"見 [維基]({WIKI_URL})。", links=WIKI_LINKS)
        self.assertEqual(out["sources"], [{"title": "維基", "url": WIKI_URL}])

    def test_bare_url_with_parentheses(self):
        out, _ = self.run_search(f"見 {WIKI_URL} 。", links=WIKI_LINKS)
        self.assertEqual([s["url"] for s in out["sources"]], [WIKI_URL])

    def test_bare_url_inside_plain_parentheses(self):
        out, _ = self.run_search("(見 https://www.python.org/downloads/)")
        self.assertEqual([s["url"] for s in out["sources"]], ["https://www.python.org/downloads/"])

    def test_only_unverified_citations_fall_back_to_search_results(self):
        """引用的全都對不上：退回搜尋結果（都是驗證過的網址），不回編造的網址。"""
        out, _ = self.run_search("見 [編的](https://made-up.example/x)。")
        self.assertEqual([s["url"] for s in out["sources"]], [
            "https://docs.python.org/3/whatsnew/3.13.html", "https://www.python.org/downloads/"])

    def test_no_search_results_means_no_sources(self):
        """（待擁有者確認的語意）沒有任何搜尋結果時，不把答案裡未驗證的網址當來源。"""
        FakePopen.instances = []
        lines = stream_without_search("見 [官方](https://made-up.example/page)。")
        with mock.patch.object(cs.subprocess, "Popen", side_effect=lambda cmd, **kw: FakePopen(cmd, lines, **kw)):
            out = cs.search("q")
        self.assertEqual(out["sources"], [])


if __name__ == "__main__":
    unittest.main()
