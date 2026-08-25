# -*- coding: utf-8 -*-
"""
tests/test_claude_subscription.py
=================================
claude_subscription 的離線測試。

全程 mock 掉 ``subprocess.run``，**不會真的呼叫 Claude、不花任何錢、不需要網路**，
也不需要本機裝過 Claude Code。可以安心在 CI 跑。

執行：
    python -m unittest discover -s tests -v
或：
    python -m unittest discover -s tests
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

# 讓測試不必先安裝套件就能 import 到專案根目錄的模組。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import claude_subscription as cs  # noqa: E402

# 有些測試會 mock 掉 subprocess.run（那是模組層級的屬性，等於全域生效）。
# Windows 上 platform.system() 第一次呼叫時內部也會用到 subprocess，會連帶壞掉。
# 先在這裡叫一次把 platform 的快取暖起來，讓測試不受執行順序影響。
_ = cs.platform.system()


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
FAKE_BINARY = "/fake/path/to/claude"


def make_payload(**overrides) -> dict:
    """產生一份「成功」的 claude JSON 輸出。"""
    payload = {
        "subtype": "success",
        "is_error": False,
        "result": "OK",
        "total_cost_usd": 0.00123,
        "session_id": "11111111-2222-3333-4444-555555555555",
        "num_turns": 1,
        "duration_ms": 1234,
        "modelUsage": {"claude-haiku": {"inputTokens": 10}},
    }
    payload.update(overrides)
    return payload


def completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    """做一個假的 CompletedProcess。"""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class BaseCase(unittest.TestCase):
    """統一把 find_claude_binary 換掉，避免測試依賴本機有沒有裝 Claude Code。"""

    def setUp(self):
        patcher = mock.patch.object(cs, "find_claude_binary", return_value=FAKE_BINARY)
        self.find_binary = patcher.start()
        self.addCleanup(patcher.stop)


# --------------------------------------------------------------------------- #
# 1. 送給 claude 的命令列長什麼樣
# --------------------------------------------------------------------------- #
class TestCommandConstruction(BaseCase):
    def _run_and_capture_cmd(self, **kwargs) -> list:
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(make_payload()))
            cs.ask("hi", **kwargs)
        return run.call_args.args[0]

    def test_defaults_are_cheap_and_toolless(self):
        """預設必須是：關閉所有工具、不留 session、帶內建精簡系統提示。"""
        cmd = self._run_and_capture_cmd()
        self.assertEqual(cmd[0], FAKE_BINARY)
        self.assertIn("-p", cmd)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "json")
        self.assertEqual(cmd[cmd.index("--model") + 1], "haiku")
        # --tools "" = 全部工具關閉，這是預設省錢又安全的關鍵
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertIn("--no-session-persistence", cmd)
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], cs._DEFAULT_SYSTEM)
        # 預設不該出現 agent 相關參數
        self.assertNotIn("--permission-mode", cmd)

    def test_prompt_is_sent_via_stdin_not_argv(self):
        """提示走 stdin，避免 Windows argv 編碼與長度限制。"""
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(make_payload()))
            cs.ask("我的中文提示")
        self.assertEqual(run.call_args.kwargs["input"], "我的中文提示")
        self.assertNotIn("我的中文提示", run.call_args.args[0])

    def test_system_none_omits_system_prompt(self):
        cmd = self._run_and_capture_cmd(system=None)
        self.assertNotIn("--system-prompt", cmd)

    def test_json_schema_is_serialized(self):
        schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
        cmd = self._run_and_capture_cmd(json_schema=schema)
        self.assertEqual(json.loads(cmd[cmd.index("--json-schema") + 1]), schema)

    def test_max_budget_and_model_passthrough(self):
        cmd = self._run_and_capture_cmd(model="sonnet", max_budget_usd=0.25)
        self.assertEqual(cmd[cmd.index("--model") + 1], "sonnet")
        self.assertEqual(cmd[cmd.index("--max-budget-usd") + 1], "0.25")

    def test_agent_mode_arguments(self):
        cmd = self._run_and_capture_cmd(tools="default", permission_mode="acceptEdits")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "default")
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "acceptEdits")

    def test_extra_args_are_appended(self):
        cmd = self._run_and_capture_cmd(extra_args=["--add-dir", "/data"])
        self.assertEqual(cmd[-2:], ["--add-dir", "/data"])

    def test_cwd_is_forwarded_to_subprocess(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(make_payload()))
            cs.ask("hi", cwd="/some/dir")
        self.assertEqual(run.call_args.kwargs["cwd"], "/some/dir")

    def test_decode_errors_are_replaced_not_raised(self):
        """claude 若吐出非 UTF-8 位元組，不能蓋掉真正的錯誤原因。"""
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(make_payload()))
            cs.ask("hi")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")


class TestSessionHandling(BaseCase):
    def _cmd(self, **kwargs) -> list:
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(make_payload()))
            cs.ask("hi", **kwargs)
        return run.call_args.args[0]

    def test_persist_keeps_session_on_disk(self):
        self.assertNotIn("--no-session-persistence", self._cmd(persist=True))

    def test_resume_implies_persist_and_skips_system_prompt(self):
        cmd = self._cmd(resume="abc-123")
        self.assertEqual(cmd[cmd.index("--resume") + 1], "abc-123")
        self.assertNotIn("--no-session-persistence", cmd)
        # 延續的 session 已經有系統提示，再覆寫會衝突
        self.assertNotIn("--system-prompt", cmd)

    def test_session_id_opens_named_session(self):
        cmd = self._cmd(session_id="uuid-here")
        self.assertEqual(cmd[cmd.index("--session-id") + 1], "uuid-here")
        self.assertNotIn("--no-session-persistence", cmd)

    def test_resume_wins_over_session_id(self):
        cmd = self._cmd(resume="r1", session_id="s1")
        self.assertIn("--resume", cmd)
        self.assertNotIn("--session-id", cmd)


# --------------------------------------------------------------------------- #
# 2. auth 模式如何處理子程序環境變數（這是「真的走訂閱」的關鍵）
# --------------------------------------------------------------------------- #
class TestAuthEnvironment(BaseCase):
    def _env_for(self, auth: str, environ: dict) -> dict:
        with mock.patch.dict(os.environ, environ, clear=True):
            with mock.patch.object(cs.subprocess, "run") as run:
                run.return_value = completed(json.dumps(make_payload()))
                cs.ask("hi", auth=auth)
            return run.call_args.kwargs["env"]

    def test_subscription_strips_api_keys(self):
        env = self._env_for(
            "subscription",
            {"ANTHROPIC_API_KEY": "sk-ant-xxx", "ANTHROPIC_AUTH_TOKEN": "tok"},
        )
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)

    def test_subscription_strips_third_party_providers(self):
        """Bedrock / Vertex / 自訂 base URL 會把請求整個導走，訂閱模式必須清掉。"""
        env = self._env_for(
            "subscription",
            {
                "CLAUDE_CODE_USE_BEDROCK": "1",
                "CLAUDE_CODE_USE_VERTEX": "1",
                "CLAUDE_CODE_USE_FOUNDRY": "1",
                "ANTHROPIC_BASE_URL": "https://proxy.example.com",
                "ANTHROPIC_CUSTOM_HEADERS": "X-Foo: bar",
            },
        )
        for var in cs._PROVIDER_ENV_VARS:
            self.assertNotIn(var, env, f"{var} 應該被清掉")

    def test_subscription_keeps_oauth_token(self):
        """CLAUDE_CODE_OAUTH_TOKEN 正是 headless 訂閱登入用的，不能清。"""
        env = self._env_for(
            "subscription", {"CLAUDE_CODE_OAUTH_TOKEN": "oauth-tok", "ANTHROPIC_API_KEY": "sk"}
        )
        self.assertEqual(env.get("CLAUDE_CODE_OAUTH_TOKEN"), "oauth-tok")

    def test_apikey_requires_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(cs.ClaudeAuthError):
                cs.ask("hi", auth="apikey")

    def test_apikey_keeps_base_url_for_proxy_users(self):
        env = self._env_for(
            "apikey",
            {"ANTHROPIC_API_KEY": "sk-ant-xxx", "ANTHROPIC_BASE_URL": "https://proxy.example.com"},
        )
        self.assertEqual(env["ANTHROPIC_API_KEY"], "sk-ant-xxx")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://proxy.example.com")

    def test_auto_touches_nothing(self):
        original = {"ANTHROPIC_API_KEY": "sk", "CLAUDE_CODE_USE_BEDROCK": "1"}
        env = self._env_for("auto", original)
        for k, v in original.items():
            self.assertEqual(env.get(k), v)

    def test_unknown_auth_mode_raises_value_error(self):
        with self.assertRaises(ValueError):
            cs.ask("hi", auth="nonsense")


# --------------------------------------------------------------------------- #
# 3. 失敗路徑：每種失敗要對應到正確的例外類別
# --------------------------------------------------------------------------- #
class TestFailureClassification(BaseCase):
    def test_timeout_becomes_claude_error(self):
        with mock.patch.object(cs.subprocess, "run", side_effect=subprocess.TimeoutExpired("c", 5)):
            with self.assertRaises(cs.ClaudeError):
                cs.ask("hi", timeout=5)

    def test_missing_executable_becomes_not_found(self):
        with mock.patch.object(cs.subprocess, "run", side_effect=OSError("no such file")):
            with self.assertRaises(cs.ClaudeNotFoundError):
                cs.ask("hi")

    def test_nonzero_exit_becomes_call_failure(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(stderr="model overloaded", returncode=1)
            with self.assertRaises(cs.ClaudeError) as ctx:
                cs.ask("hi")
        self.assertNotIsInstance(ctx.exception, cs.ClaudeAuthError)

    def test_nonzero_exit_with_auth_wording_becomes_auth_error(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(stderr="Error: Invalid API key", returncode=1)
            with self.assertRaises(cs.ClaudeAuthError):
                cs.ask("hi")

    def test_unparseable_json_becomes_call_failure(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed("this is not json")
            with self.assertRaises(cs.ClaudeError):
                cs.ask("hi")

    def test_is_error_payload_becomes_call_failure(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(make_payload(is_error=True, subtype="error")))
            with self.assertRaises(cs.ClaudeError):
                cs.ask("hi")

    def test_http_401_becomes_auth_error(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(
                json.dumps(make_payload(is_error=True, subtype="error", api_error_status=401))
            )
            with self.assertRaises(cs.ClaudeAuthError):
                cs.ask("hi")

    def test_auth_marker_detection(self):
        self.assertTrue(cs._looks_like_auth_failure("Error: UNAUTHORIZED"))
        self.assertTrue(cs._looks_like_auth_failure("", "oauth token has expired"))
        self.assertFalse(cs._looks_like_auth_failure("rate limit exceeded"))
        self.assertFalse(cs._looks_like_auth_failure(""))

    def test_not_found_error_is_still_a_file_not_found_error(self):
        """向後相容：舊程式碼可能寫 except FileNotFoundError。"""
        self.assertTrue(issubclass(cs.ClaudeNotFoundError, FileNotFoundError))
        self.assertTrue(issubclass(cs.ClaudeAuthError, cs.ClaudeError))


# --------------------------------------------------------------------------- #
# 4. 執行檔解析
# --------------------------------------------------------------------------- #
class TestBinaryResolution(unittest.TestCase):
    def test_explicit_existing_path_is_used(self):
        self.assertEqual(cs._resolve_binary(sys.executable), sys.executable)

    def test_explicit_missing_path_gives_friendly_error(self):
        with self.assertRaises(cs.ClaudeNotFoundError) as ctx:
            cs._resolve_binary("/definitely/not/here/claude")
        # 要給安裝指引，而不是裸的 WinError 2
        self.assertIn("CLAUDE_BINARY", str(ctx.exception))

    def test_bare_name_falls_back_to_path_lookup(self):
        with mock.patch.object(cs.shutil, "which", return_value="/usr/bin/claude"):
            self.assertEqual(cs._resolve_binary("claude"), "/usr/bin/claude")

    def test_no_binary_argument_delegates_to_autodetect(self):
        with mock.patch.object(cs, "find_claude_binary", return_value="/auto/claude") as f:
            self.assertEqual(cs._resolve_binary(None), "/auto/claude")
        f.assert_called_once()


# --------------------------------------------------------------------------- #
# 5. 結果物件與附檔
# --------------------------------------------------------------------------- #
class TestResultAndAttachments(BaseCase):
    def test_result_fields_are_mapped(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(make_payload(result="hello")))
            r = cs.ask("hi")
        self.assertEqual(r.text, "hello")
        self.assertAlmostEqual(r.cost_usd, 0.00123)
        self.assertEqual(r.session_id, "11111111-2222-3333-4444-555555555555")
        self.assertEqual(r.num_turns, 1)
        self.assertEqual(r.duration_ms, 1234)
        self.assertIn("claude-haiku", r.model_usage)
        self.assertEqual(r.raw["subtype"], "success")

    def test_data_prefers_structured_output(self):
        r = cs.ClaudeResult(text='{"a": 1}', cost_usd=0.0, structured_output={"b": 2})
        self.assertEqual(r.data, {"b": 2})

    def test_data_falls_back_to_parsing_text(self):
        r = cs.ClaudeResult(text='{"a": 1}', cost_usd=0.0)
        self.assertEqual(r.data, {"a": 1})

    def test_data_raises_on_unparseable_text(self):
        with self.assertRaises(ValueError):
            cs.ClaudeResult(text="not json", cost_usd=0.0).data

    def test_attachments_are_wrapped_with_filename_headers(self):
        with TemporaryDirectory() as td:
            f = Path(td) / "note.txt"
            f.write_text("內容在這", encoding="utf-8")
            blob = cs._read_attachments([str(f)])
        self.assertIn("note.txt", blob)
        self.assertIn("內容在這", blob)

    def test_attachment_strips_bom(self):
        with TemporaryDirectory() as td:
            f = Path(td) / "bom.txt"
            f.write_bytes("﻿hello".encode("utf-8"))
            blob = cs._read_attachments([str(f)])
        self.assertNotIn("﻿", blob)

    def test_missing_attachment_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            cs._read_attachments(["/no/such/file.txt"])

    def test_binary_attachment_raises_value_error_with_guidance(self):
        with TemporaryDirectory() as td:
            f = Path(td) / "img.png"
            f.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\xfd")
            with self.assertRaises(ValueError) as ctx:
                cs._read_attachments([str(f)])
        self.assertIn("--tools Read", str(ctx.exception))

    def test_attachments_are_prepended_to_prompt(self):
        with TemporaryDirectory() as td:
            f = Path(td) / "a.txt"
            f.write_text("DATA", encoding="utf-8")
            with mock.patch.object(cs.subprocess, "run") as run:
                run.return_value = completed(json.dumps(make_payload()))
                cs.ask("問題", attach=[str(f)])
        sent = run.call_args.kwargs["input"]
        self.assertTrue(sent.index("DATA") < sent.index("問題"))


# --------------------------------------------------------------------------- #
# 6. CLI：結束碼契約（其他語言就是靠這個分辨失敗原因）
# --------------------------------------------------------------------------- #
class TestCliExitCodes(BaseCase):
    def _main(self, argv: list) -> tuple:
        """跑 _main，回傳 (exit_code, stdout, stderr)。"""
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = cs._main(argv)
        except SystemExit as e:  # argparse 錯誤 / --version
            code = e.code
        return code, out.getvalue(), err.getvalue()

    def test_success_returns_zero(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(make_payload(result="answer")))
            code, out, _ = self._main(["hi"])
        self.assertEqual(code, cs.EXIT_OK)
        self.assertEqual(out.strip(), "answer")

    def test_call_failure_returns_one(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(stderr="overloaded", returncode=1)
            code, _, err = self._main(["hi"])
        self.assertEqual(code, cs.EXIT_CALL_FAILED)
        self.assertIn("錯誤", err)

    def test_missing_binary_returns_two(self):
        self.find_binary.side_effect = cs.ClaudeNotFoundError("nope")
        code, _, _ = self._main(["hi"])
        self.assertEqual(code, cs.EXIT_NO_BINARY)

    def test_bad_binary_flag_returns_two(self):
        code, _, err = self._main(["--binary", "/no/such/claude", "hi"])
        self.assertEqual(code, cs.EXIT_NO_BINARY)
        self.assertIn("CLAUDE_BINARY", err)

    def test_auth_failure_returns_three(self):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(stderr="Invalid API key", returncode=1)
            code, _, err = self._main(["hi"])
        self.assertEqual(code, cs.EXIT_NOT_AUTHENTICATED)
        self.assertIn("認證", err)

    def test_missing_apikey_returns_three(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            code, _, _ = self._main(["--auth", "apikey", "hi"])
        self.assertEqual(code, cs.EXIT_NOT_AUTHENTICATED)

    def test_missing_attachment_returns_four(self):
        code, _, err = self._main(["--attach", "/no/such.txt", "hi"])
        self.assertEqual(code, cs.EXIT_BAD_INPUT)
        self.assertIn("輸入錯誤", err)

    def test_argparse_error_returns_four_not_two(self):
        """argparse 預設用 2，會跟「找不到執行檔」撞號，必須改成 4。"""
        code, _, _ = self._main(["--model"])  # 缺少值
        self.assertEqual(code, cs.EXIT_BAD_INPUT)

    def test_mutually_exclusive_session_flags_return_four(self):
        code, _, _ = self._main(["--resume", "a", "--continue", "hi"])
        self.assertEqual(code, cs.EXIT_BAD_INPUT)

    def test_missing_prompt_file_returns_four(self):
        code, _, _ = self._main(["--prompt-file", "/no/such.txt"])
        self.assertEqual(code, cs.EXIT_BAD_INPUT)

    def test_bad_schema_file_returns_four(self):
        with TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            code, _, _ = self._main(["--json-schema-file", str(bad), "hi"])
        self.assertEqual(code, cs.EXIT_BAD_INPUT)

    def test_bad_cwd_returns_four(self):
        code, _, _ = self._main(["--cwd", "/no/such/dir", "hi"])
        self.assertEqual(code, cs.EXIT_BAD_INPUT)

    def test_empty_prompt_returns_four(self):
        code, _, _ = self._main(["   "])
        self.assertEqual(code, cs.EXIT_BAD_INPUT)

    def test_interactive_stdin_does_not_hang(self):
        """沒給提示又在互動終端機時，要立刻報錯而不是靜默卡住等 stdin。"""
        fake_stdin = mock.Mock()
        fake_stdin.isatty.return_value = True
        with mock.patch.object(cs.sys, "stdin", fake_stdin):
            code, _, _ = self._main([])
        self.assertEqual(code, cs.EXIT_BAD_INPUT)
        fake_stdin.buffer.read.assert_not_called()

    def test_which_success_and_failure(self):
        code, out, _ = self._main(["--which"])
        self.assertEqual(code, cs.EXIT_OK)
        self.assertEqual(out.strip(), FAKE_BINARY)

        self.find_binary.side_effect = cs.ClaudeNotFoundError("nope")
        code, _, _ = self._main(["--which"])
        self.assertEqual(code, cs.EXIT_NO_BINARY)

    def test_version_flag(self):
        code, out, _ = self._main(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(cs.__version__, out)


# --------------------------------------------------------------------------- #
# 7. CLI：輸出格式
# --------------------------------------------------------------------------- #
class TestCliOutput(BaseCase):
    def _main(self, argv: list, payload: dict) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(payload))
            with redirect_stdout(out), redirect_stderr(err):
                code = cs._main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_text_format_prints_only_the_answer(self):
        _, out, err = self._main(["hi"], make_payload(result="just this"))
        self.assertEqual(out.strip(), "just this")
        self.assertEqual(err, "")  # 診斷不能污染 stdout，也不該無故印到 stderr

    def test_json_format_shape(self):
        _, out, _ = self._main(["--format", "json", "hi"], make_payload(result="a"))
        obj = json.loads(out)
        self.assertEqual(
            set(obj),
            {"text", "structured_output", "session_id", "cost_usd", "model", "duration_ms"},
        )
        self.assertEqual(obj["text"], "a")

    def test_structured_output_is_printed_as_json(self):
        payload = make_payload(result="好的，已完成", structured_output={"n": 2})
        _, out, _ = self._main(["hi"], payload)
        self.assertEqual(json.loads(out), {"n": 2})

    def test_show_cost_goes_to_stderr_only(self):
        _, out, err = self._main(["--show-cost", "hi"], make_payload(result="a"))
        self.assertEqual(out.strip(), "a")
        self.assertIn("花費", err)

    def test_output_file_is_written(self):
        with TemporaryDirectory() as td:
            target = Path(td) / "out.txt"
            self._main(["--output-file", str(target), "hi"], make_payload(result="saved"))
            self.assertEqual(target.read_text(encoding="utf-8"), "saved")

    def test_non_ascii_is_not_escaped_in_json(self):
        _, out, _ = self._main(["--format", "json", "hi"], make_payload(result="中文"))
        self.assertIn("中文", out)


# --------------------------------------------------------------------------- #
# 8. CLI：agent 參數有沒有真的傳下去
# --------------------------------------------------------------------------- #
class TestCliAgentFlags(BaseCase):
    def _cmd(self, argv: list) -> list:
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(make_payload()))
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                cs._main(argv)
        return run.call_args.args[0]

    def test_permission_mode_reaches_claude(self):
        cmd = self._cmd(["--tools", "default", "--permission-mode", "acceptEdits", "hi"])
        self.assertEqual(cmd[cmd.index("--tools") + 1], "default")
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "acceptEdits")

    def test_claude_arg_passthrough_is_repeatable(self):
        """透傳的參數幾乎一定以 - 開頭，argparse 預設收不下，必須先正規化。"""
        cmd = self._cmd(["--claude-arg", "--add-dir", "--claude-arg", "/data", "hi"])
        self.assertEqual(cmd[-2:], ["--add-dir", "/data"])

    def test_claude_arg_equals_form_also_works(self):
        cmd = self._cmd(["--claude-arg=--fork-session", "hi"])
        self.assertEqual(cmd[-1], "--fork-session")

    def test_continue_flag_is_passed_through(self):
        cmd = self._cmd(["--continue", "hi"])
        self.assertIn("--continue", cmd)
        self.assertNotIn("--no-session-persistence", cmd)
        self.assertNotIn("--system-prompt", cmd)  # 延續時不覆寫系統提示

    def test_invalid_permission_mode_is_rejected(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cs._main(["--permission-mode", "nope", "hi"])
        self.assertEqual(ctx.exception.code, cs.EXIT_BAD_INPUT)

    def test_cwd_reaches_subprocess(self):
        with TemporaryDirectory() as td:
            with mock.patch.object(cs.subprocess, "run") as run:
                run.return_value = completed(json.dumps(make_payload()))
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    cs._main(["--cwd", td, "hi"])
            self.assertEqual(run.call_args.kwargs["cwd"], td)


# --------------------------------------------------------------------------- #
# 9. 透傳參數的 argv 正規化
# --------------------------------------------------------------------------- #
class TestPassthroughNormalization(unittest.TestCase):
    def test_dash_prefixed_value_is_merged(self):
        self.assertEqual(
            cs._normalize_passthrough(["--claude-arg", "--add-dir", "x"]),
            ["--claude-arg=--add-dir", "x"],
        )

    def test_other_arguments_are_untouched(self):
        argv = ["--model", "sonnet", "--format", "json", "hi"]
        self.assertEqual(cs._normalize_passthrough(argv), argv)

    def test_double_dash_stops_rewriting(self):
        """-- 之後是位置參數，讓使用者能傳以 - 開頭的提示。"""
        argv = ["--", "--claude-arg", "-starts-with-dash"]
        self.assertEqual(cs._normalize_passthrough(argv), argv)

    def test_trailing_flag_without_value_is_left_for_argparse(self):
        self.assertEqual(cs._normalize_passthrough(["--claude-arg"]), ["--claude-arg"])

    def test_prompt_starting_with_dash_survives_double_dash(self):
        with mock.patch.object(cs, "find_claude_binary", return_value=FAKE_BINARY):
            with mock.patch.object(cs.subprocess, "run") as run:
                run.return_value = completed(json.dumps(make_payload()))
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = cs._main(["--", "-減號開頭的提示"])
        self.assertEqual(code, cs.EXIT_OK)
        self.assertEqual(run.call_args.kwargs["input"], "-減號開頭的提示")


# --------------------------------------------------------------------------- #
# 10. check_setup 的結束碼
# --------------------------------------------------------------------------- #
class TestCheckSetup(BaseCase):
    """check_setup 的職責是「把各種失敗對應到正確的結束碼」，所以這裡直接 mock
    掉 ask()，而不是 subprocess.run——patch subprocess.run 會連 platform.system()
    內部用到的 subprocess 一起換掉。"""

    def _check(self, **kwargs) -> int:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return cs.check_setup(**kwargs)

    def test_missing_binary_returns_two(self):
        self.find_binary.side_effect = cs.ClaudeNotFoundError("nope")
        self.assertEqual(self._check(), cs.EXIT_NO_BINARY)

    def test_apikey_without_key_returns_three(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self._check(auth="apikey", do_ping=False), cs.EXIT_NOT_AUTHENTICATED)

    def test_no_ping_skips_the_call_entirely(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "t"}, clear=True):
            with mock.patch.object(cs, "ask") as ask:
                code = self._check(do_ping=False)
        self.assertEqual(code, cs.EXIT_OK)
        ask.assert_not_called()  # --no-ping 必須完全不花錢

    def test_no_ping_without_credentials_returns_three(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(cs.Path, "home", return_value=Path("/no/such/home")):
                code = self._check(do_ping=False)
        self.assertEqual(code, cs.EXIT_NOT_AUTHENTICATED)

    def test_successful_ping_returns_zero(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "t"}, clear=True):
            with mock.patch.object(cs, "ask", return_value=cs.ClaudeResult(text="OK", cost_usd=0.001)):
                code = self._check()
        self.assertEqual(code, cs.EXIT_OK)

    def test_unexpected_reply_returns_one(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "t"}, clear=True):
            with mock.patch.object(cs, "ask", return_value=cs.ClaudeResult(text="???", cost_usd=0.0)):
                code = self._check()
        self.assertEqual(code, cs.EXIT_CALL_FAILED)

    def test_auth_failure_during_ping_returns_three(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "t"}, clear=True):
            with mock.patch.object(cs, "ask", side_effect=cs.ClaudeAuthError("bad token")):
                code = self._check()
        self.assertEqual(code, cs.EXIT_NOT_AUTHENTICATED)

    def test_other_failure_during_ping_returns_one(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "t"}, clear=True):
            with mock.patch.object(cs, "ask", side_effect=cs.ClaudeError("overloaded")):
                code = self._check()
        self.assertEqual(code, cs.EXIT_CALL_FAILED)

    def test_binary_vanishing_during_ping_returns_two(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "t"}, clear=True):
            with mock.patch.object(cs, "ask", side_effect=cs.ClaudeNotFoundError("gone")):
                code = self._check()
        self.assertEqual(code, cs.EXIT_NO_BINARY)

    def test_bad_auth_mode_returns_four(self):
        self.assertEqual(self._check(auth="nonsense"), cs.EXIT_BAD_INPUT)


if __name__ == "__main__":
    unittest.main()
