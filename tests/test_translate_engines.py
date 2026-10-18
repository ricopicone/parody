"""Translation engines: Claude Code on the subscription, or the API (task #825)."""

import builtins
import json
import subprocess

import pytest

from parody.translate.engines import (
    AnthropicAPIEngine,
    ClaudeCodeEngine,
    EngineError,
    make_engine,
)
from parody.translate.languages import TranslationConfig


class _Run:
    """Stands in for subprocess.run and records what it was given."""

    def __init__(self, stdout="", returncode=0, stderr=""):
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.result


def _ok(text):
    return json.dumps({"type": "result", "subtype": "success",
                       "is_error": False, "result": text})


def test_claude_code_strips_api_credentials(monkeypatch):
    # Either variable would make Claude Code bill the API, not the subscription.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    run = _Run(_ok("x"))
    monkeypatch.setattr(subprocess, "run", run)
    ClaudeCodeEngine("claude-opus-5-5").complete("sys", "user")
    env = run.calls[0][1]["env"]
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env
    assert env.get("PATH")


def test_claude_code_argv(monkeypatch):
    run = _Run(_ok("x"))
    monkeypatch.setattr(subprocess, "run", run)
    ClaudeCodeEngine("claude-opus-5-5").complete("SYSTEM", "USER")
    argv, kwargs = run.calls[0]
    assert argv == ["claude", "-p", "--output-format", "json", "--model", "claude-opus-5-5",
                    "--tools", "", "--no-session-persistence", "--strict-mcp-config",
                    "--disable-slash-commands", "--setting-sources", "",
                    "--system-prompt", "SYSTEM"]
    assert "--bare" not in argv
    assert kwargs["input"] == "USER"


def test_claude_code_returns_result(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _Run(_ok("<<<chunk 1>>>\nX")))
    assert ClaudeCodeEngine("m").complete("s", "u") == "<<<chunk 1>>>\nX"


@pytest.mark.parametrize("run", [
    _Run(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                     "result": "Usage limit reached"})),
    _Run(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": False,
                     "result": ""})),
    _Run("", returncode=1, stderr="boom"),
    _Run("not json"),
])
def test_claude_code_errors_raise(monkeypatch, run):
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(EngineError):
        ClaudeCodeEngine("m").complete("s", "u")


def test_claude_code_missing_executable(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("claude")
    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(EngineError, match="Claude Code"):
        ClaudeCodeEngine("m").complete("s", "u")


def test_api_engine_missing_package_message(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("no anthropic")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(EngineError, match=r"parody\[translate-api\]"):
        AnthropicAPIEngine("claude-opus-5-5").complete("s", "u")


def test_make_engine():
    cc = make_engine(TranslationConfig(languages=("zh",)))
    assert isinstance(cc, ClaudeCodeEngine) and cc.model == "claude-opus-5-5"
    assert cc.name == "claude-code"
    api = make_engine(TranslationConfig(languages=("zh",), engine="anthropic-api", model="m"))
    assert isinstance(api, AnthropicAPIEngine) and api.name == "anthropic-api"
