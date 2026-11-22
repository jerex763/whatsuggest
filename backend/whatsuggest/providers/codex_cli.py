"""Codex CLI provider.

Uses `codex exec` in non-interactive mode so Florence's existing Codex login
(`~/.codex/auth.json` from `codex login`) is reused. No API key is required.

Flags follow the current Codex CLI reference (learn.chatgpt.com, `codex exec`):

- prompt `-` reads the prompt from stdin, which avoids Windows `.cmd` wrappers
  mangling multiline arguments
- `--output-schema FILE` requests a final message matching a JSON Schema
- `--output-last-message` / `-o FILE` writes that final message to disk
- `--sandbox read-only` is the default automation sandbox; this call only needs text
- `--skip-git-repo-check` allows an empty workspace that is not a git repo
- `--ephemeral` skips saving a session rollout
- `--cd` points Codex at an empty directory so it has nothing to browse
- `--color never` keeps the final message free of ANSI codes

`--full-auto` is not used; current docs say it is no longer supported.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from whatsuggest.config import CodexSettings

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "suggestions.schema.json"
_API_KEY_VARS = ("OPENAI_API_KEY", "CODEX_API_KEY")


class CodexError(RuntimeError):
    """`codex exec` failed, timed out, or returned nothing usable."""


class CodexCLIProvider:
    def __init__(self, settings: CodexSettings, runner=None, platform: str | None = None) -> None:
        self.settings = settings
        self._runner = runner or subprocess.run
        self._platform = platform or os.name

    def generate(self, prompt: str) -> str:
        exe = resolve_codex_executable(self.settings.command or None, platform=self._platform)
        workdir = Path(tempfile.mkdtemp(prefix="whatsuggest-codex-"))
        schema = workdir / "schema.json"
        output = workdir / "last-message.json"
        try:
            schema.write_text(SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            argv = build_codex_argv(
                exe,
                schema_path=str(schema),
                output_path=str(output),
                workdir=str(workdir),
                settings=self.settings,
                platform=self._platform,
            )
            env = _child_env(self.settings)
            log.info("running codex exec (sandbox=%s, ephemeral=%s)", self.settings.sandbox, self.settings.ephemeral)
            try:
                completed = self._runner(
                    argv,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.settings.timeout_seconds,
                    cwd=str(workdir),
                    env=env,
                    **_run_kwargs(self._platform),
                )
            except subprocess.TimeoutExpired as exc:
                raise CodexError(f"codex timed out after {self.settings.timeout_seconds}s") from exc
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            if completed.returncode != 0:
                detail = (stderr or stdout).strip()[-500:]
                raise CodexError(f"codex exited {completed.returncode}: {detail}")
            text = _read_output(output, stdout)
            if not text.strip():
                raise CodexError("codex returned an empty message")
            return text
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


def build_codex_argv(
    exe: str,
    *,
    schema_path: str,
    output_path: str,
    workdir: str,
    settings: CodexSettings,
    platform: str,
) -> list[str]:
    args = [
        exe,
        "exec",
        "-",
        "--color",
        "never",
        "--sandbox",
        settings.sandbox,
        "--cd",
        workdir,
        "--output-schema",
        schema_path,
        "--output-last-message",
        output_path,
    ]
    if settings.skip_git_repo_check:
        args.append("--skip-git-repo-check")
    if settings.ephemeral:
        args.append("--ephemeral")
    if settings.ignore_user_config:
        args.append("--ignore-user-config")
    if settings.model:
        args.extend(["--model", settings.model])
    args.extend(settings.extra_args)
    return wrap_windows_cmd(args, platform)


def wrap_windows_cmd(argv: list[str], platform: str) -> list[str]:
    """Run a `.cmd` / `.bat` shim through `cmd.exe` without putting the prompt on the command line.

    The previous Claude integration hit this: `shutil.which` returns `claude.CMD`,
    and CreateProcess plus the cmd shim splits multiline arguments. The prompt is
    passed on stdin (`codex exec -`), so the command line stays single-line.
    A native `codex.exe` is invoked directly.
    """
    exe = argv[0]
    if platform == "nt" and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(argv)]
    return list(argv)


def resolve_codex_executable(
    configured: str | None = None,
    *,
    which=None,
    exists=None,
    platform: str | None = None,
    env: dict | None = None,
) -> str:
    platform = platform or os.name
    exists = exists or os.path.exists
    which = which or shutil.which
    env = env if env is not None else os.environ
    if configured:
        if exists(configured):
            return _prefer_exe(configured, exists, platform)
        raise CodexError(f"codex command not found: {configured}")
    found = which("codex")
    if not found and platform == "nt":
        found = _windows_candidate(env, exists)
    if not found:
        raise CodexError(
            "codex CLI not found. Install it and run `codex login`, or set llm.codex.command."
        )
    return _prefer_exe(found, exists, platform)


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _prefer_exe(path: str, exists, platform: str) -> str:
    if platform != "nt" or not path.lower().endswith((".cmd", ".bat")):
        return path
    sibling = os.path.join(os.path.dirname(path), "codex.exe")
    if exists(sibling):
        return sibling
    return path


def _windows_candidate(env: dict, exists) -> str | None:
    local = env.get("LOCALAPPDATA", "")
    profile = env.get("USERPROFILE", "")
    appdata = env.get("APPDATA", "")
    candidates = [
        os.path.join(local, "Programs", "OpenAI", "Codex", "codex.exe"),
        os.path.join(profile, ".codex", "codex.exe"),
        os.path.join(appdata, "npm", "codex.cmd"),
    ]
    for candidate in candidates:
        if candidate and exists(candidate):
            return candidate
    return None


def _child_env(settings: CodexSettings) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if not settings.use_api_key:
        for name in _API_KEY_VARS:
            env.pop(name, None)
    return env


def _run_kwargs(platform: str) -> dict:
    if platform == "nt":
        flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if flag:
            return {"creationflags": flag}
    return {}


def _read_output(path: Path, stdout: str) -> str:
    if path.is_file():
        file_text = path.read_text(encoding="utf-8", errors="replace").strip()
        if file_text:
            return file_text
    return stdout.strip()
