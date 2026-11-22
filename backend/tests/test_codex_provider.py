import json
from pathlib import Path

import pytest

from whatsuggest.config import CodexSettings, OpenAISettings
from whatsuggest.providers.codex_cli import (
    CodexCLIProvider,
    CodexError,
    build_codex_argv,
    resolve_codex_executable,
    wrap_windows_cmd,
)
from whatsuggest.providers.openai_api import OpenAIAPIProvider


def test_argv_uses_exec_schema_and_stdin_prompt():
    settings = CodexSettings(model="gpt-5.1-codex", sandbox="read-only", extra_args=["--ignore-rules"])
    argv = build_codex_argv(
        "codex",
        schema_path="/tmp/schema.json",
        output_path="/tmp/out.json",
        workdir="/tmp/empty",
        settings=settings,
        platform="posix",
    )
    assert argv[:3] == ["codex", "exec", "-"]
    assert "--output-schema" in argv
    assert "--output-last-message" in argv
    assert "--skip-git-repo-check" in argv
    assert "--ephemeral" in argv
    assert "--sandbox" in argv and "read-only" in argv
    assert "--cd" in argv
    assert "--model" in argv and "gpt-5.1-codex" in argv
    assert "--ignore-rules" in argv
    assert "mcp" not in " ".join(argv).lower()
    joined = " ".join(argv)
    assert "suggestions" not in joined  # the prompt is not on the command line


def test_windows_cmd_wrapper_quotes_without_embedding_prompt():
    argv = wrap_windows_cmd(
        ["C:\\npm\\codex.cmd", "exec", "-", "--output-schema", "C:\\My Dir\\schema.json"],
        "nt",
    )
    assert argv[0] == "cmd.exe"
    assert argv[1:4] == ["/d", "/s", "/c"]
    assert "codex.cmd" in argv[4]
    assert "exec" in argv[4]
    assert "schema.json" in argv[4]
    native = wrap_windows_cmd(["C:\\Codex\\codex.exe", "exec", "-"], "nt")
    assert native[0].endswith("codex.exe")


def test_resolve_prefers_sibling_exe(tmp_path: Path):
    cmd = tmp_path / "codex.cmd"
    exe = tmp_path / "codex.exe"
    cmd.write_text("@echo off\r\n", encoding="utf-8")
    exe.write_text("", encoding="utf-8")
    found = resolve_codex_executable(
        str(cmd),
        exists=lambda p: Path(p).exists(),
        platform="nt",
    )
    assert found.endswith("codex.exe")


def test_resolve_missing_command():
    with pytest.raises(CodexError):
        resolve_codex_executable(
            None,
            which=lambda _name: None,
            exists=lambda _p: False,
            platform="posix",
            env={},
        )


def test_generate_reads_output_file_and_strips_api_keys(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("CODEX_API_KEY", "sk-codex")
    seen = {}

    def runner(argv, input, capture_output, text, encoding, errors, timeout, cwd, env, **kwargs):
        seen["argv"] = argv
        seen["prompt"] = input
        seen["env"] = env
        out_index = argv.index("--output-last-message") + 1
        Path(argv[out_index]).write_text('{"suggestions":["a","b","c"]}\n', encoding="utf-8")

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    provider = CodexCLIProvider(CodexSettings(command="codex", use_api_key=False), runner=runner, platform="posix")
    # command "codex" must exist for resolve. Point at a real file.
    fake = tmp_path / "codex"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    provider.settings.command = str(fake)
    text = provider.generate("draft three replies")
    assert json.loads(text)["suggestions"] == ["a", "b", "c"]
    assert seen["prompt"] == "draft three replies"
    assert "OPENAI_API_KEY" not in seen["env"]
    assert "CODEX_API_KEY" not in seen["env"]
    assert seen["argv"][1:3] == ["exec", "-"]


def test_generate_nonzero_exit(tmp_path: Path):
    def runner(*_args, **_kwargs):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "boom"

        return Result()

    fake = tmp_path / "codex"
    fake.write_text("", encoding="utf-8")
    provider = CodexCLIProvider(CodexSettings(command=str(fake)), runner=runner, platform="posix")
    with pytest.raises(CodexError, match="exited 1"):
        provider.generate("hi")


def test_openai_body_is_structured_and_has_no_send_tool(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured = {}

    def transport(url, body, api_key, timeout):
        captured["url"] = url
        captured["body"] = body
        captured["key"] = api_key
        return json.dumps({"choices": [{"message": {"content": '{"suggestions":["a","b","c"]}'}}]})

    provider = OpenAIAPIProvider(OpenAISettings(model="gpt-4.1-mini"), transport=transport)
    text = provider.generate("hello")
    assert "suggestions" in text
    body = captured["body"]
    assert body["model"] == "gpt-4.1-mini"
    schema = body["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert "tools" not in body
    assert captured["key"] == "sk-test"
    assert captured["url"].endswith("/chat/completions")
