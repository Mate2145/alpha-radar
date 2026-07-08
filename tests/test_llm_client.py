from types import SimpleNamespace
import subprocess

import pytest

from app.summarization import llm_client
from app.summarization.llm_client import LLMClient


def settings(**overrides: object) -> SimpleNamespace:
    values = {
        "llm_provider": "fallback",
        "openai_api_key": None,
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o-mini",
        "openrouter_api_key": None,
        "openrouter_base_url": "https://openrouter.ai/api/v1",
        "openrouter_model": "openai/gpt-4o-mini",
        "codex_model": None,
        "codex_command": "codex",
        "codex_timeout_seconds": 180,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"choices": [{"message": {"content": "router digest"}}]}


def test_openrouter_uses_openai_compatible_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: settings(llm_provider="openrouter", openrouter_api_key="or-key"),
    )

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)

    client = LLMClient()

    assert client.complete("system", "user") == "router digest"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer or-key"}
    assert captured["json"] == {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        "temperature": 0.2,
    }


def test_codex_cli_runs_codex_exec_with_prompt_on_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: settings(llm_provider="codex_cli", codex_model="gpt-5.4"),
    )

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="codex digest\n", stderr="")

    monkeypatch.setattr(llm_client.subprocess, "run", fake_run)

    client = LLMClient()

    assert client.complete("system prompt", "user prompt") == "codex digest"
    assert captured["command"] == [
        "codex",
        "exec",
        "--ephemeral",
        "--model",
        "gpt-5.4",
        "system prompt",
    ]
    assert captured["input"] == "user prompt"
    assert captured["text"] is True
    assert captured["capture_output"] is True
    assert captured["timeout"] == 180
    assert captured["check"] is False


def test_codex_cli_surfaces_command_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: settings(llm_provider="codex_cli"),
    )
    monkeypatch.setattr(
        llm_client.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="not logged in"),
    )

    with pytest.raises(RuntimeError, match="not logged in"):
        LLMClient().complete("system", "user")


def test_codex_cli_surfaces_missing_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: settings(llm_provider="codex_cli", codex_command="missing-codex"),
    )
    monkeypatch.setattr(
        llm_client.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    with pytest.raises(RuntimeError, match="Codex CLI command not found"):
        LLMClient().complete("system", "user")


def test_codex_cli_surfaces_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: settings(llm_provider="codex_cli", codex_timeout_seconds=1),
    )
    monkeypatch.setattr(
        llm_client.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd="codex", timeout=1)
        ),
    )

    with pytest.raises(RuntimeError, match="timed out"):
        LLMClient().complete("system", "user")


def test_codex_cli_rejects_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: settings(llm_provider="codex_cli"),
    )
    monkeypatch.setattr(
        llm_client.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="  \n", stderr=""),
    )

    with pytest.raises(RuntimeError, match="returned no content"):
        LLMClient().complete("system", "user")
