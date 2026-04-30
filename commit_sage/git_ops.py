"""Git operations for Git-Commit-Sage."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from commit_sage.exceptions import GitError

logger = logging.getLogger("commit_sage")


def _run_git(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a git command and return the result. Raises GitError on failure."""
    try:
        return subprocess.run(
            cmd, text=True, capture_output=True, check=True
        )
    except subprocess.CalledProcessError as e:
        raise GitError(e.stderr.strip() or f"git {' '.join(cmd)} 失败") from e
    except FileNotFoundError:
        raise GitError("未找到 git 命令，请确认已安装 Git") from None


def git_add_all() -> None:
    """Stage all changes."""
    logger.info("git add -A ...")
    _run_git(["git", "add", "-A"])


def get_git_diff(staged_only: bool = True) -> str:
    """Return git diff output."""
    cmd = ["git", "diff", "--cached"] if staged_only else ["git", "diff"]
    return _run_git(cmd).stdout


def get_git_status() -> str:
    """Return short git status for context."""
    try:
        return _run_git(["git", "status", "--short"]).stdout
    except GitError:
        return ""


def get_changed_files(staged_only: bool = True) -> list[str]:
    """Return list of changed file paths."""
    cmd = ["git", "diff", "--cached", "--name-only"] if staged_only else ["git", "diff", "--name-only"]
    try:
        out = _run_git(cmd).stdout.strip()
        return [p for p in out.split("\n") if p]
    except GitError:
        return []


def infer_scope(files: list[str]) -> str:
    """Infer a scope from changed file paths."""
    if not files:
        return ""
    dirs: dict[str, int] = {}
    for f in files:
        parts = Path(f).parts
        if len(parts) >= 2:
            dirs[parts[0]] = dirs.get(parts[0], 0) + 1
        else:
            ext = Path(f).suffix
            if ext:
                dirs[ext.lstrip(".")] = dirs.get(ext.lstrip("."), 0) + 1
    if dirs:
        return max(dirs, key=dirs.get)
    return ""


def git_commit(message: str, dry_run: bool = False) -> None:
    """Execute git commit."""
    if dry_run:
        logger.info("[DRY RUN] 将执行: git commit -m %s", repr(message))
        print("\n[dry-run] 以上提交信息已生成，但未实际提交。")
        return
    result = _run_git(["git", "commit", "-m", message])
    logger.info("提交成功！\n%s", result.stdout.strip())
