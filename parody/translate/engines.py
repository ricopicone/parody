"""What actually translates: Claude, by one of two routes (task #825).

``claude-code`` runs Claude Code headless (``claude -p``) on the author's own
login, so a translation run draws on the Claude subscription, not API
billing. That holds only while no API credential is in the environment: in
``-p`` mode Claude Code uses ``ANTHROPIC_API_KEY`` whenever it is set. So
both credential variables are removed from the child's environment. Never
add ``--bare``, which ignores the subscription login altogether.

``anthropic-api`` calls the Messages API with an API key, for CI later on.
The prompt and the checks are the same either way; only the transport
differs.
"""

import json
import os
import subprocess
from typing import Protocol

_API_CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


class EngineError(Exception):
    pass


class Engine(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


class ClaudeCodeEngine:
    name = "claude-code"

    def __init__(self, model, executable="claude", timeout=3600):
        self.model = model
        self.executable = executable
        self.timeout = timeout

    def complete(self, system, user):
        argv = [self.executable, "-p", "--output-format", "json", "--model", self.model,
                # A pure text job: no tools, no MCP servers, no skills, no
                # settings or hooks. That keeps the overhead to ~600 tokens.
                "--tools", "", "--no-session-persistence", "--strict-mcp-config",
                "--disable-slash-commands", "--setting-sources", "",
                "--system-prompt", system]
        env = {k: v for k, v in os.environ.items() if k not in _API_CREDENTIALS}
        try:
            proc = subprocess.run(argv, input=user, capture_output=True, text=True,
                                  env=env, timeout=self.timeout)
        except FileNotFoundError as e:
            raise EngineError(
                f"Claude Code ({self.executable!r}) is not installed or not on PATH") from e
        except subprocess.TimeoutExpired as e:
            raise EngineError(f"Claude Code timed out after {self.timeout}s") from e
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise EngineError(
                f"Claude Code exited {proc.returncode}: "
                f"{(proc.stderr or proc.stdout).strip()[:500]}") from None
        if proc.returncode or out.get("is_error") or out.get("subtype") != "success":
            raise EngineError(
                f"Claude Code failed ({out.get('subtype')}): {str(out.get('result'))[:500]}")
        return out.get("result") or ""


class AnthropicAPIEngine:
    name = "anthropic-api"

    def __init__(self, model):
        self.model = model

    def complete(self, system, user):
        try:
            import anthropic
        except ImportError as e:
            raise EngineError(
                "the anthropic-api engine needs the SDK: "
                "pip install 'parody[translate-api]'") from e
        client = anthropic.Anthropic()
        # Server-side fallback on a policy refusal, routed by category.
        with client.beta.messages.stream(
                model=self.model, max_tokens=64000, system=system,
                messages=[{"role": "user", "content": user}],
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"}) as stream:
            message = stream.get_final_message()
        if message.stop_reason in ("refusal", "max_tokens"):
            raise EngineError(f"the API stopped with {message.stop_reason}")
        return "".join(b.text for b in message.content if b.type == "text")


def make_engine(config):
    if config.engine == "anthropic-api":
        return AnthropicAPIEngine(config.model)
    return ClaudeCodeEngine(config.model)
