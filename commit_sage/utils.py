"""Utility functions for Git-Commit-Sage."""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

from commit_sage.config import CONVENTIONAL_COMMIT_TYPES, MAX_DIFF_CHARS

logger = logging.getLogger("commit_sage")


def _truncate_diff(diff: str) -> str:
    if len(diff) > MAX_DIFF_CHARS:
        logger.warning(
            "diff 较长 (%d 字符)，截取前 %d 字符", len(diff), MAX_DIFF_CHARS
        )
        return diff[:MAX_DIFF_CHARS]
    return diff


def build_user_prompt(
    diff: str,
    status: str,
    scope: str,
    custom_prompt: Optional[str] = None,
) -> str:
    """Build the user prompt for the AI."""
    if custom_prompt:
        return custom_prompt

    parts = []
    if status:
        parts.append(f"文件变更状态:\n{status}")
    if scope:
        parts.append(f"建议 scope: {scope}")
    parts.append(
        "请根据以下代码改动，生成 Conventional Commits 规范的提交信息:\n\n" + diff
    )
    return "\n\n".join(parts)


def extract_first_line(message: str) -> str:
    """Extract the first line of the commit message."""
    return message.strip().split("\n")[0].strip()


def validate_conventional_commit(message: str) -> Tuple[bool, str]:
    """Validate that the message follows Conventional Commits specification."""
    line = extract_first_line(message)
    pattern = r"^(\w+)(\([\w\-./]+\))?!?: .+"
    match = re.match(pattern, line)
    if not match:
        return False, f"格式不符合 Conventional Commits: {line}"
    ctype = match.group(1)
    if ctype not in CONVENTIONAL_COMMIT_TYPES:
        return False, f"type '{ctype}' 不在标准类型中 ({', '.join(sorted(CONVENTIONAL_COMMIT_TYPES))})"
    if len(line) > 72:
        return False, f"摘要超过 72 字符 ({len(line)} 字符)"
    return True, ""


def display_usage(usage: dict) -> None:
    """Display token usage information."""
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", prompt_tokens + completion_tokens)
    if total > 0:
        print(
            "Token 用量 — prompt: {}, completion: {}, total: {}".format(
                prompt_tokens, completion_tokens, total
            )
        )


def parse_commit_parts(message: str) -> Tuple[str, str, str]:
    """Parse a commit message into (subject, scope, body)."""
    lines = message.strip().split("\n")
    subject = lines[0].strip()
    body = "\n".join(lines[1:]).strip()

    pattern = r"^(\w+)(\(([\w\-./]*)\))?(!)?: (.+)$"
    match = re.match(pattern, subject)
    if match:
        scope = match.group(3) or ""
    else:
        scope = ""

    return subject, scope, body


def rebuild_subject(subject: str, new_scope: str) -> str:
    """Replace or add scope in the subject line."""
    pattern = r"^(\w+)(\([\w\-./]*\))?(!)?: (.+)$"
    match = re.match(pattern, subject)
    if not match:
        return subject

    ctype = match.group(1)
    breaking = match.group(3) or ""
    desc = match.group(4)

    if new_scope:
        return f"{ctype}({new_scope}){breaking}: {desc}"
    else:
        return f"{ctype}{breaking}: {desc}"
