"""CLI interface for Git-Commit-Sage."""

from __future__ import annotations

import argparse
import re
from typing import Optional

from commit_sage.git_ops import git_commit
from commit_sage.utils import parse_commit_parts, rebuild_subject


def confirm_and_commit(
    message: str, dry_run: bool = False
) -> None:
    """Interactive confirmation and commit flow with scope/body editing."""
    _display_message(message)

    while True:
        print(
            "  [y] 确认提交  [e] 编辑全文  [s] 编辑 scope  "
            "[b] 编辑 body  [n] 取消"
        )
        choice = input("选择 (y/e/s/b/n): ").strip().lower()

        if choice == "y":
            git_commit(message, dry_run)
            break
        elif choice == "e":
            print("\n编辑提交信息 (可直接按 Enter 取消):")
            edited = input("> ").strip()
            if not edited:
                print("已取消。")
                break
            _display_message(edited)
            confirm = input("确认提交? (y/n): ").strip().lower()
            if confirm == "y":
                git_commit(edited, dry_run)
            else:
                print("已取消。")
            break
        elif choice == "s":
            message = _edit_scope(message)
            _display_message(message)
        elif choice == "b":
            message = _edit_body(message)
            _display_message(message)
        elif choice == "n":
            print("已取消。")
            break


def _display_message(message: str) -> None:
    print("\n" + "━" * 50)
    print("建议的提交信息:")
    print("━" * 50)
    print(message)
    print("━" * 50 + "\n")


def _edit_scope(message: str) -> str:
    subject, scope, body = parse_commit_parts(message)
    print(f"\n当前 scope: {scope or '(无)'}")
    new_scope = input("新 scope (直接回车清除 scope): ").strip()
    new_subject = rebuild_subject(subject, new_scope)
    if body:
        return new_subject + "\n" + body
    return new_subject


def _edit_body(message: str) -> str:
    subject, _, body = parse_commit_parts(message)
    print(f"\n当前 body:\n{body or '(无)'}\n")
    print("输入新 body (直接回车保持不变):")
    new_body = input("> ").strip()
    if new_body:
        return subject + "\n" + new_body
    return message


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Git-Commit-Sage — AI 驱动的 Git 提交助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  commit_sage.py                        分析暂存区改动\n"
            "  commit_sage.py -a                     自动 git add 全部改动\n"
            "  commit_sage.py --diff                 分析未暂存改动 (仅预览)\n"
            "  commit_sage.py -p                     仅预览 AI 建议，不提交\n"
            "  commit_sage.py --provider ollama      使用 Ollama 本地模型\n"
            "  commit_sage.py --prompt \"用英文写\"   自定义用户 prompt\n"
            "  commit_sage.py -q                    仅输出提交信息到 stdout"
        ),
    )

    git_grp = parser.add_argument_group("Git 选项")
    git_grp.add_argument(
        "-a", "--all", action="store_true",
        help="自动 git add 所有改动文件后再分析",
    )
    git_grp.add_argument(
        "--diff", action="store_true",
        help="分析未暂存的改动 (git diff，不包含新文件)",
    )
    git_grp.add_argument(
        "--dry-run", action="store_true",
        help="生成提交信息但不实际执行 git commit",
    )

    ai_grp = parser.add_argument_group("AI 选项")
    ai_grp.add_argument(
        "--provider", default=None,
        choices=["openai", "deepseek", "ollama"],
        help="AI 提供商 (默认: 从 .env 读取)",
    )
    ai_grp.add_argument(
        "-m", "--model", default=None,
        help="指定模型名称 (覆盖 .env 中的 MODEL)",
    )
    ai_grp.add_argument(
        "--url", default=None,
        help="API 地址 (覆盖 .env 中的 API_URL)",
    )
    ai_grp.add_argument(
        "--prompt", default=None,
        help="自定义用户 prompt 模板",
    )
    ai_grp.add_argument(
        "--system-prompt", default=None,
        help="自定义系统 prompt (也可通过 .env 中的 SYSTEM_PROMPT 设置)",
    )
    ai_grp.add_argument(
        "--timeout", type=int, default=None,
        help="API 请求超时秒数 (默认: 60)",
    )
    ai_grp.add_argument(
        "--ollama-host", default=None,
        help="Ollama 服务地址 (默认: http://localhost:11434)",
    )

    out_grp = parser.add_argument_group("输出选项")
    out_grp.add_argument(
        "-p", "--preview", action="store_true",
        help="仅显示 AI 建议，不执行 git commit",
    )
    out_grp.add_argument(
        "-q", "--quiet", action="store_true",
        help="静默模式，仅输出提交信息文本到 stdout",
    )
    out_grp.add_argument(
        "-v", "--verbose", action="store_true",
        help="详细输出，显示调试信息",
    )

    return parser
