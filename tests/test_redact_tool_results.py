"""Secrets a tool reads never reach the model in clear text."""
import pytest

from jarvis.tools.registry import run_tool_with_retries, BUILTIN_TOOLS
from jarvis.tools.types import ToolExecutionResult
from jarvis.utils.redact import redact, scrub_secrets

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("line, secret", [
    ("OLLAMA_EMBEDDING_PASS=minhaSenha123", "minhaSenha123"),
    ("PROXY_LLM_TOKEN=abc123def456", "abc123def456"),
    ("BRAVE_API_KEY=bsk_9f8e7d6c", "bsk_9f8e7d6c"),
    ("db_password: hunter2", "hunter2"),
    ("SERVICE_SECRET = s3cr3t", "s3cr3t"),
])
def test_prefixed_credential_names_are_masked(line, secret):
    for scrub in (redact, scrub_secrets):
        masked = scrub(line)
        assert secret not in masked
        assert "[REDACTED]" in masked


def test_ordinary_text_about_keys_is_kept():
    text = "The key point = growth, and the monkey = happy."

    assert scrub_secrets(text) == text


class _LeakyTool:
    name = "leakyTestTool"

    def execute(self, **_kwargs):
        return ToolExecutionResult(
            success=True,
            reply_text="Line one\nOLLAMA_EMBEDDING_PASS=minhaSenha123\nLine three",
        )


def test_tool_results_are_scrubbed_before_the_model_sees_them(monkeypatch, mock_config):
    monkeypatch.setitem(BUILTIN_TOOLS, "leakyTestTool", _LeakyTool())

    result = run_tool_with_retries(
        db=None, cfg=mock_config, tool_name="leakyTestTool", tool_args={},
        system_prompt="", original_prompt="", redacted_text="", max_retries=0,
    )

    assert result.success
    assert "minhaSenha123" not in result.reply_text
    assert result.reply_text.splitlines()[0] == "Line one"
    assert result.reply_text.splitlines()[2] == "Line three"
