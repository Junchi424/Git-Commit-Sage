"""Main entry point for Git-Commit-Sage."""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from commit_sage.cli import build_parser, confirm_and_commit
from commit_sage.config import Config
from commit_sage.exceptions import (
    AIAuthError,
    AIError,
    AIResponseError,
    AITimeoutError,
    ConfigError,
    GitError,
)
from commit_sage.git_ops import get_git_diff, git_add_all
from commit_sage.providers import create_provider
from commit_sage.utils import (
    _truncate_diff,
    display_usage,
    validate_conventional_commit,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger("commit_sage")


def main(argv: Optional[list[str]] = None) -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    # -- Load config ------------------------------------------------------
    try:
        config = Config.from_env()
    except Exception as e:
        logger.error("加载配置失败: %s", e)
        sys.exit(1)

    # -- Apply CLI overrides ----------------------------------------------
    if args.provider:
        config.provider = args.provider
    if args.model:
        config.model = args.model
    if args.url:
        config.api_url = args.url
    if args.ollama_host:
        config.ollama_host = args.ollama_host
    if args.timeout is not None:
        config.timeout = args.timeout
    if args.preview:
        config.preview_only = True
    if args.dry_run:
        config.dry_run = True
    if args.all:
        config.auto_add = True
    if args.diff:
        config.diff_mode = True
    if args.prompt:
        config.custom_prompt = args.prompt

    # system-prompt from CLI or env
    if args.system_prompt:
        config.system_prompt = args.system_prompt
    elif os.getenv("SYSTEM_PROMPT"):
        config.system_prompt = os.getenv("SYSTEM_PROMPT")

    config.resolve_defaults()

    try:
        config.validate()
    except ConfigError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.debug(
        "Provider: %s | Model: %s | URL: %s",
        config.provider, config.model, config.api_url,
    )

    # -- Auto-add ---------------------------------------------------------
    if config.auto_add:
        try:
            git_add_all()
        except GitError as e:
            logger.error(str(e))
            sys.exit(1)

    # -- Get diff ---------------------------------------------------------
    staged_only = not config.diff_mode
    try:
        diff = get_git_diff(staged_only)
    except GitError as e:
        logger.error(str(e))
        sys.exit(1)

    if not diff.strip():
        if not config.diff_mode:
            logger.warning(
                "暂存区为空，请先 git add 文件，或使用 -a 自动添加"
            )
        else:
            logger.warning("未检测到未暂存的代码改动")
        sys.exit(0)

    # -- Generate commit message ------------------------------------------
    if not config.quiet:
        logger.info("AI 正在分析代码改动...")

    try:
        diff = _truncate_diff(diff)
        provider = create_provider(config)
        message, usage = provider.generate(diff)
    except AIAuthError as e:
        logger.error(str(e))
        sys.exit(1)
    except AITimeoutError as e:
        logger.error(str(e))
        sys.exit(1)
    except AIResponseError as e:
        logger.error(str(e))
        sys.exit(1)
    except AIError as e:
        logger.error("AI 错误: %s", e)
        sys.exit(1)

    # -- Quiet mode: just print the message -------------------------------
    if config.quiet:
        print(message)
        return

    # -- Display result ---------------------------------------------------
    print(f"\n{message}\n")

    is_valid, warning = validate_conventional_commit(message)
    if not is_valid:
        logger.warning("⚠ %s", warning)

    display_usage(usage)

    if config.preview_only:
        logger.info("预览模式，跳过提交")
        return

    confirm_and_commit(message, dry_run=config.dry_run)


if __name__ == "__main__":
    main()
