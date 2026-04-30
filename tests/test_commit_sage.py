"""Tests for Git-Commit-Sage."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from commit_sage import (
    AIAuthError,
    AIResponseError,
    AITimeoutError,
    Config,
    ConfigError,
    GitError,
    _truncate_diff,
    build_user_prompt,
    extract_first_line,
    infer_scope,
    validate_conventional_commit,
)


# ── Config Tests ──────────────────────────────────────────────────────
class TestConfig:
    def test_validate_missing_api_key(self):
        config = Config(provider="openai", api_key="")
        with pytest.raises(ConfigError, match="API_KEY"):
            config.validate()

    def test_validate_ollama_no_key_needed(self):
        config = Config(provider="ollama", api_key="")
        config.validate()  # should not raise

    def test_resolve_defaults_openai(self):
        config = Config(provider="openai")
        config.resolve_defaults()
        assert "api.openai.com" in config.api_url
        assert config.model == "gpt-4o-mini"

    def test_resolve_defaults_deepseek(self):
        config = Config(provider="deepseek")
        config.resolve_defaults()
        assert "api.deepseek.com" in config.api_url
        assert config.model == "deepseek-chat"

    def test_resolve_defaults_no_override_if_set(self):
        config = Config(provider="openai", api_url="https://custom.api/v1", model="custom-model")
        config.resolve_defaults()
        assert config.api_url == "https://custom.api/v1"
        assert config.model == "custom-model"

    def test_resolve_defaults_unknown_provider(self):
        config = Config(provider="unknown", api_url="https://example.com/api")
        config.resolve_defaults()
        assert config.model == "gpt-4o-mini"  # fallback


# ── Truncate Diff Tests ───────────────────────────────────────────────
class TestTruncateDiff:
    def test_short_diff_not_truncated(self):
        diff = "short diff"
        assert _truncate_diff(diff) == diff

    def test_long_diff_truncated(self):
        diff = "x" * 10000
        result = _truncate_diff(diff)
        assert len(result) == 8000

    def test_empty_diff(self):
        assert _truncate_diff("") == ""


# ── Build User Prompt Tests ───────────────────────────────────────────
class TestBuildUserPrompt:
    def test_basic(self):
        p = build_user_prompt("diff content", "", "", None)
        assert "diff content" in p
        assert "Conventional Commits" in p

    def test_with_status(self):
        p = build_user_prompt("diff", "M file.py", "", None)
        assert "M file.py" in p

    def test_with_scope(self):
        p = build_user_prompt("diff", "", "components", None)
        assert "components" in p

    def test_custom_prompt_overrides(self):
        p = build_user_prompt("diff", "status", "scope", "custom prompt text")
        assert p == "custom prompt text"


# ── Extract First Line Tests ──────────────────────────────────────────
class TestExtractFirstLine:
    def test_single_line(self):
        assert extract_first_line("feat: add login") == "feat: add login"

    def test_multiline(self):
        msg = "feat: add login\n\nAdded login endpoint.\nCloses #42"
        assert extract_first_line(msg) == "feat: add login"

    def test_strips_whitespace(self):
        assert extract_first_line("  feat: foo  \n\nbody") == "feat: foo"


# ── Validate Conventional Commit Tests ────────────────────────────────
class TestValidateConventionalCommit:
    def test_valid_feat(self):
        ok, _ = validate_conventional_commit("feat: add login feature")
        assert ok

    def test_valid_with_scope(self):
        ok, _ = validate_conventional_commit("fix(parser): handle null input")
        assert ok

    def test_breaking_change(self):
        ok, _ = validate_conventional_commit("feat!: drop support for Python 3.8")
        assert ok

    def test_invalid_format(self):
        ok, msg = validate_conventional_commit("invalid commit message")
        assert not ok

    def test_invalid_type(self):
        ok, msg = validate_conventional_commit("badtype: something")
        assert not ok
        assert "badtype" in msg

    def test_too_long_summary(self):
        long_msg = "feat: " + "a" * 70
        ok, msg = validate_conventional_commit(long_msg)
        assert not ok


# ── Infer Scope Tests ─────────────────────────────────────────────────
class TestInferScope:
    def test_single_file_deep_path(self):
        assert infer_scope(["src/utils/helpers.py"]) == "src"

    def test_dominant_directory(self):
        files = [
            "src/components/Button.tsx",
            "src/components/Modal.tsx",
            "tests/test_app.py",
        ]
        assert infer_scope(files) == "src"

    def test_extension_fallback(self):
        files = ["main.py", "utils.py"]
        assert infer_scope(files) == "py"

    def test_empty(self):
        assert infer_scope([]) == ""


# ── Git Operations Tests ──────────────────────────────────────────────
class TestGitAddAll:
    @patch("commit_sage._run_git")
    def test_success(self, mock_run):
        from commit_sage import git_add_all
        git_add_all()
        mock_run.assert_called_once_with(["git", "add", "-A"])

    @patch("commit_sage._run_git")
    def test_failure(self, mock_run):
        from commit_sage import git_add_all
        mock_run.side_effect = GitError("fail")
        with pytest.raises(GitError, match="fail"):
            git_add_all()


class TestGetGitDiff:
    @patch("commit_sage._run_git")
    def test_staged(self, mock_run):
        mock_run.return_value = MagicMock(stdout="diff here")
        from commit_sage import get_git_diff
        result = get_git_diff(staged_only=True)
        assert result == "diff here"
        mock_run.assert_called_once_with(["git", "diff", "--cached"])

    @patch("commit_sage._run_git")
    def test_unstaged(self, mock_run):
        mock_run.return_value = MagicMock(stdout="unstaged diff")
        from commit_sage import get_git_diff
        result = get_git_diff(staged_only=False)
        assert result == "unstaged diff"
        mock_run.assert_called_once_with(["git", "diff"])


class TestRunGit:
    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        from commit_sage import _run_git
        result = _run_git(["git", "status"])
        assert result.stdout == "ok"

    @patch("subprocess.run")
    def test_called_process_error(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "git", stderr="error msg")
        from commit_sage import _run_git
        with pytest.raises(GitError, match="error msg"):
            _run_git(["git", "status"])

    @patch("subprocess.run")
    def test_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("No git")
        from commit_sage import _run_git
        with pytest.raises(GitError, match="未找到 git 命令"):
            _run_git(["git", "status"])


# ── AI Provider Tests ─────────────────────────────────────────────────
class TestOpenAIProvider:
    @patch("commit_sage.requests.post")
    def test_success(self, mock_post, monkeypatch):
        monkeypatch.setenv("API_KEY", "sk-test")
        from commit_sage import OpenAIProvider
        config = Config(api_key="sk-test", api_url="https://api.test/v1", model="test-model")
        provider = OpenAIProvider(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "feat: test commit"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_post.return_value = mock_resp

        msg, usage = provider.generate("fake diff")
        assert msg == "feat: test commit"
        assert usage["total_tokens"] == 15

    @patch("commit_sage.requests.post")
    def test_auth_error_401(self, mock_post):
        from commit_sage import OpenAIProvider
        config = Config(api_key="bad-key", api_url="https://api.test/v1", model="test")
        provider = OpenAIProvider(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        with pytest.raises(AIAuthError):
            provider.generate("diff")

    @patch("commit_sage.requests.post")
    def test_timeout(self, mock_post):
        import requests as req
        from commit_sage import OpenAIProvider
        config = Config(api_key="k", api_url="https://api.test/v1", model="m")
        provider = OpenAIProvider(config)

        mock_post.side_effect = req.exceptions.Timeout

        with pytest.raises(AITimeoutError):
            provider.generate("diff")
