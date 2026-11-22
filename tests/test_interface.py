# -*- coding: utf-8 -*-
"""
tests/test_interface.py
=======================
統一呼叫介面（三個訂閱登入套件共用的名字）的離線測試：訊息清單、Result 的 usage／model、錯誤階層。

全程 mock 掉子程序，**不會真的呼叫 Claude、不連網**。

執行：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import claude_subscription as cs  # noqa: E402

_ = cs.platform.system()        # 暖 platform 的快取（見 test_claude_subscription.py）

FAKE_BINARY = "/fake/path/to/claude"


def payload(**overrides) -> dict:
    data = {"subtype": "success", "is_error": False, "result": "OK", "total_cost_usd": 0.001,
            "session_id": "s-1", "num_turns": 1, "duration_ms": 5, "modelUsage": {}}
    data.update(overrides)
    return data


def completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class Base(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(cs, "find_claude_binary", return_value=FAKE_BINARY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_ask(self, prompt, out=None, **kwargs):
        with mock.patch.object(cs.subprocess, "run") as run:
            run.return_value = completed(json.dumps(out or payload()))
            result = cs.ask(prompt, **kwargs)
        return result, run.call_args.args[0], run.call_args.kwargs["input"]


class TestNames(unittest.TestCase):
    def test_old_names_still_import(self):
        from claude_subscription import (ask, ask_stream, ClaudeError, ClaudeAuthError,  # noqa: F401
                                         ClaudeNotFoundError, ClaudeUsageLimitError)

    def test_unified_names_are_aliases_not_new_classes(self):
        self.assertIs(cs.Result, cs.ClaudeResult)
        self.assertIs(cs.UsageLimitError, cs.ClaudeUsageLimitError)
        self.assertIs(cs.AuthError, cs.ClaudeAuthError)
        self.assertIs(cs.NotInstalledError, cs.ClaudeNotFoundError)
        self.assertIs(cs.CallTimeoutError, cs.ClaudeTimeoutError)
        self.assertEqual(cs.INTERFACE_VERSION, "1")
        for name in ("INTERFACE_VERSION", "CAPABILITIES", "Result", "LoginError", "UsageLimitError", "AuthError",
                     "NotInstalledError", "CallTimeoutError", "flatten_messages"):
            self.assertIn(name, cs.__all__)

    def test_hierarchy_keeps_old_catch_behaviour(self):
        for cls in (cs.ClaudeError, cs.ClaudeAuthError, cs.ClaudeUsageLimitError, cs.ClaudeTimeoutError,
                    cs.ClaudeIsolationUnsupportedError, cs.ClaudeNotFoundError):
            self.assertTrue(issubclass(cls, cs.LoginError), cls)
        # 舊的關係一條都不變
        self.assertTrue(issubclass(cs.ClaudeError, RuntimeError))
        self.assertTrue(issubclass(cs.ClaudeNotFoundError, FileNotFoundError))
        self.assertFalse(issubclass(cs.ClaudeNotFoundError, cs.ClaudeError))
        self.assertTrue(issubclass(cs.ClaudeTimeoutError, cs.ClaudeError))
        self.assertEqual(cs.ClaudeUsageLimitError.__name__, "ClaudeUsageLimitError")

    def test_kinds(self):
        self.assertEqual(cs.LoginError("x").kind, "unknown")
        self.assertEqual(cs.ClaudeError("x").kind, "unknown")
        self.assertEqual(cs.ClaudeUsageLimitError("x").kind, "quota_exhausted")
        self.assertEqual(cs.ClaudeAuthError("x").kind, "auth_invalid")
        self.assertEqual(cs.ClaudeNotFoundError("x").kind, "not_installed")
        self.assertEqual(cs.ClaudeTimeoutError("x").kind, "timeout")
        err = cs.ClaudeUsageLimitError("x", resets="7pm")
        self.assertEqual((err.resets, err.retry_after), ("7pm", None))

    def test_capabilities_are_honest(self):
        caps = cs.CAPABILITIES
        self.assertFalse(caps["tools"])
        self.assertFalse(caps["images"])
        self.assertTrue(caps["stream"])
        self.assertEqual(caps["messages"], "flattened")
        self.assertEqual(caps["interface"], cs.INTERFACE_VERSION)


class TestFlatten(unittest.TestCase):
    def test_string_passes_through(self):
        self.assertEqual(cs.flatten_messages("hi"), (None, "hi"))
        self.assertEqual(cs.flatten_messages("hi", "S"), ("S", "hi"))

    def test_single_user_message_is_sent_as_is(self):
        msgs = [{"role": "system", "content": "S1"}, {"role": "user", "content": "hello"}]
        self.assertEqual(cs.flatten_messages(msgs), ("S1", "hello"))
        self.assertEqual(cs.flatten_messages(msgs, "S0"), ("S0\n\nS1", "hello"))

    def test_multi_turn_becomes_transcript(self):
        class Msg:
            def __init__(self, role, content):
                self.role, self.content = role, content

        system, prompt = cs.flatten_messages([Msg("user", "a"), Msg("assistant", "b"),
                                              Msg("user", [{"type": "text", "text": "c"}])])
        self.assertIsNone(system)
        self.assertTrue(prompt.startswith(cs._MULTI_TURN_HEAD))
        self.assertTrue(prompt.endswith("### User\na\n\n### Assistant\nb\n\n### User\nc"))

    def test_rejects_what_it_cannot_do(self):
        bad = [
            [{"role": "tool", "content": "x"}, {"role": "user", "content": "y"}],
            [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:,"}}]}],
            [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
            [],
            [{"role": "system", "content": "only system"}],
        ]
        for msgs in bad:
            with self.assertRaises(ValueError, msg=msgs):
                cs.flatten_messages(msgs)
        with self.assertRaises(ValueError):
            cs.flatten_messages(None)
        with self.assertRaises(ValueError):
            cs.flatten_messages({"role": "user", "content": "x"})


class TestAskWithMessages(Base):
    def test_messages_system_goes_to_system_prompt(self):
        msgs = [{"role": "system", "content": "be brief"}, {"role": "user", "content": "你好"}]
        _r, cmd, stdin = self.run_ask(msgs)
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], "be brief")
        self.assertEqual(stdin, "你好")

    def test_explicit_system_is_kept_and_messages_system_appended(self):
        msgs = [{"role": "system", "content": "B"}, {"role": "user", "content": "q"}]
        _r, cmd, _ = self.run_ask(msgs, system="A")
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], "A\n\nB")

    def test_messages_without_system_keep_the_default(self):
        _r, cmd, stdin = self.run_ask([{"role": "user", "content": "q"}])
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], cs._DEFAULT_SYSTEM)
        self.assertEqual(stdin, "q")

    def test_string_prompt_unchanged(self):
        _r, cmd, stdin = self.run_ask("plain")
        self.assertEqual(stdin, "plain")
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], cs._DEFAULT_SYSTEM)

    def test_model_none_means_haiku(self):
        _r, cmd, _ = self.run_ask("x", model=None)
        self.assertEqual(cmd[cmd.index("--model") + 1], "haiku")

    def test_ask_stream_takes_messages_too(self):
        seen = {}

        def fake_stream(claude, cmd, env, prompt, cwd, timeout, on_event, *, redact):
            seen.update(cmd=cmd, prompt=prompt)
            return cs.ClaudeResult(text="ok", cost_usd=0.0)

        with mock.patch.object(cs, "_run_stream", side_effect=fake_stream):
            r = cs.ask_stream([{"role": "system", "content": "S"}, {"role": "user", "content": "q"}],
                              lambda e: None)
        self.assertEqual(seen["prompt"], "q")
        self.assertEqual(seen["cmd"][seen["cmd"].index("--system-prompt") + 1], "S")
        self.assertEqual(r.model, "haiku")


class TestResultShape(Base):
    def test_model_and_usage_from_usage_block(self):
        out = payload(usage={"input_tokens": 10, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 5,
                             "output_tokens": 7},
                      modelUsage={"claude-haiku-x": {"outputTokens": 1}, "claude-sonnet-y": {"outputTokens": 9}})
        r, _cmd, _ = self.run_ask("x", out=out, model="sonnet")
        self.assertEqual(r.model, "claude-sonnet-y")
        self.assertEqual(r.usage, {"input": 18, "output": 7, "cached_input": 5})

    def test_usage_falls_back_to_model_usage(self):
        out = payload(modelUsage={"m": {"inputTokens": 4, "cacheReadInputTokens": 2, "outputTokens": 3}})
        r, _cmd, _ = self.run_ask("x", out=out)
        self.assertEqual(r.usage, {"input": 6, "output": 3, "cached_input": 2})
        self.assertEqual(r.model, "m")

    def test_nothing_known(self):
        r, _cmd, _ = self.run_ask("x", model="opus")
        self.assertEqual((r.usage, r.model), ({}, "opus"))
        self.assertEqual(cs.ClaudeResult(text="t", cost_usd=0.0).usage, {})


class TestErrors(Base):
    def test_timeout_is_a_claude_error_and_call_timeout(self):
        with mock.patch.object(cs.subprocess, "run", side_effect=subprocess.TimeoutExpired("claude", 3)):
            with self.assertRaises(cs.ClaudeError) as ctx:
                cs.ask("x", timeout=3)
        self.assertIsInstance(ctx.exception, cs.CallTimeoutError)
        self.assertEqual(ctx.exception.kind, "timeout")
        self.assertEqual(str(ctx.exception), "呼叫逾時（3s）。")

    def test_usage_limit_is_unified(self):
        out = payload(is_error=True, subtype="error_during_execution", api_error_status=429,
                      result="You've hit your limit · resets 7pm (Asia/Taipei)")
        with mock.patch.object(cs.subprocess, "run", return_value=completed(json.dumps(out))):
            with self.assertRaises(cs.UsageLimitError) as ctx:
                cs.ask("x")
        self.assertEqual(ctx.exception.kind, "quota_exhausted")
        self.assertIsNone(ctx.exception.retry_after)
        self.assertTrue(ctx.exception.resets)

    def test_auth_is_unified(self):
        with mock.patch.object(cs.subprocess, "run", return_value=completed("", "Not logged in", 1)):
            with self.assertRaises(cs.AuthError) as ctx:
                cs.ask("x")
        self.assertIsInstance(ctx.exception, cs.LoginError)

    def test_not_installed_is_unified(self):
        with mock.patch.object(cs, "find_claude_binary", side_effect=cs.ClaudeNotFoundError("none")):
            with self.assertRaises(cs.NotInstalledError) as ctx:
                cs.ask("x")
        self.assertIsInstance(ctx.exception, cs.LoginError)
        self.assertIsInstance(ctx.exception, FileNotFoundError)


if __name__ == "__main__":
    unittest.main()
