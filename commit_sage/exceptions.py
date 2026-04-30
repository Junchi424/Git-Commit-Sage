"""Custom exceptions for Git-Commit-Sage."""

from __future__ import annotations


class CommitSageError(Exception):
    """Base exception."""


class GitError(CommitSageError):
    """Git operations failed."""


class ConfigError(CommitSageError):
    """Configuration invalid."""


class AIError(CommitSageError):
    """AI provider error."""


class AITimeoutError(AIError):
    """API timeout."""


class AIAuthError(AIError):
    """Authentication failed (401/402/403)."""


class AIResponseError(AIError):
    """API responded with error or unexpected format."""
