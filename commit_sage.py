#!/usr/bin/env python3
"""Git-Commit-Sage — AI-powered Git commit message generator."""

from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict

import requests

# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger("commit_sage")

# ── Constants ──────────────────────────────────────────────────────────
MAX_DIFF_CHARS = 8000

CONVENTIONAL_COMMIT_TYPES: set[str] = {
    "feat", "fix", "docs", "style", "refactor",
    "perf", "test", "chore", "ci", "build", "revert",
}

DEFAULT_SYSTEM_PROMPT = (
    "你是一个专业的 Git 提交信息助手。"
    "根据代码改动生成符合 Conventional Commits 规范的提交信息。\n\n"
    "要求:\n"
    "1. 格式: <type>[scope]: <简短描述>\n"
    "2. type 必须是: feat, fix, docs, style, refactor, perf, test, chore, ci, build, revert\n"
    "3. 描述单行不超过 72 字符，首字母小写\n"
    "4. 如果有重大改动，添加 BREAKING CHANGE 脚注\n"
    "5. 只输出提交信息，不要解释"
)

PROVIDER_DEFAULTS: Dict[str, Dict[str, str]] = {
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    },
    "deepseek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
    },
    "ollama": {
        "url": "http://localhost:11434/api/chat",
        "model": "llama3",
    },
}


# ── Exceptions ─────────────────────────────────────────────────────────
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


# ── Configuration ──────────────────────────────────────────────────────
@dataclass
class Config:
    """Application configuration from .env and CLI args."""

    api_key: str = ""
    api_url: str = ""
    model: str = ""
    provider: str = "openai"
    ollama_host: str = "http://localhost:11434"
    timeout: int = 60
    preview_only: bool = False
    auto_add: bool = False
    diff_mode: bool = False
    custom_prompt: Optional[str] = None
    system_prompt: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from .env file and environment variables."""
        cls._load_dotenv()
        return cls(
            api_key=os.getenv("API_KEY", ""),
            api_url=os.getenv("API_URL", ""),
            model=os.getenv("MODEL", ""),
            provider=os.getenv("PROVIDER", "openai").lower(),
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            timeout=int(os.getenv("TIMEOUT", "60")),
        )

    @staticmethod
    def _load_dotenv() -> None:
        env_path = Path(__file__).parent / ".env"
        if not env_path.exists():
            return
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value and key not in os.environ:
                    os.environ[key] = value

    def validate(self) -> None:
        """Validate required configuration fields."""
        if self.provider == "ollama":
            return
        if not self.api_key:
            raise ConfigError(
                "未配置 API_KEY。\n\n"
                "方法1: 复制 .env.example 为 .env，填入你的 API Key\n"
                "方法2: 设置环境变量  export API_KEY=你的密钥"
            )

    def resolve_defaults(self) -> None:
        """Fill in default url / model for the selected provider."""
        defaults = PROVIDER_DEFAULTS.get(self.provider, {})
        if not self.api_url:
            self.api_url = defaults.get("url", "")
        if not self.model:
            self.model = defaults.get("model", "gpt-4o-mini")


# ── Git Operations ─────────────────────────────────────────────────────
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


def git_commit(message: str) -> None:
    """Execute git commit."""
    result = _run_git(["git", "commit", "-m", message])
    logger.info("提交成功！\n%s", result.stdout.strip())


# ── Commit Message Helpers ─────────────────────────────────────────────
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
        logger.info(
            "Token 用量 — prompt: %d, completion: %d, total: %d",
            prompt_tokens, completion_tokens, total,
        )


# ── AI Providers ───────────────────────────────────────────────────────
class OpenAIProvider:
    """OpenAI-compatible chat completions API."""

    def __init__(self, config: Config):
        self.config = config

    def generate(self, diff: str) -> Tuple[str, dict]:
        sys_prompt = self.config.system_prompt or DEFAULT_SYSTEM_PROMPT
        user_prompt = build_user_prompt(
            diff,
            get_git_status(),
            infer_scope(get_changed_files()),
            self.config.custom_prompt,
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        data = {"model": self.config.model, "messages": messages}

        try:
            resp = requests.post(
                self.config.api_url,
                headers=headers,
                json=data,
                timeout=self.config.timeout,
            )
        except requests.exceptions.Timeout:
            raise AITimeoutError("API 请求超时，请检查网络或 API 地址") from None
        except requests.exceptions.ConnectionError:
            raise AITimeoutError("无法连接 API 服务器，请检查 API_URL 和网络") from None

        self._handle_status(resp)

        try:
            body = resp.json()
        except ValueError:
            raise AIResponseError(f"API 返回非 JSON 格式: {resp.text[:200]}") from None

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AIResponseError(
                f"API 返回格式异常，缺少 choices[0].message.content: {str(body)[:300]}"
            ) from None

        usage = body.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        return content.strip(), usage

    @staticmethod
    def _handle_status(resp: requests.Response) -> None:
        if resp.status_code == 401:
            raise AIAuthError("API Key 无效，请检查 API_KEY 配置")
        if resp.status_code == 402:
            raise AIAuthError("API 余额不足，请检查账户额度")
        if resp.status_code == 403:
            raise AIAuthError("API 访问被拒绝，请检查 API Key 权限")
        if resp.status_code == 429:
            raise AIResponseError("API 请求频率过高，请稍后重试")
        if resp.status_code >= 500:
            raise AIResponseError(f"API 服务器错误 (HTTP {resp.status_code})")
        if resp.status_code != 200:
            raise AIResponseError(f"API 请求失败 (HTTP {resp.status_code})")


class OllamaProvider:
    """Ollama local LLM provider."""

    def __init__(self, config: Config):
        self.config = config
        self.api_url = f"{config.ollama_host}/api/chat"

    def generate(self, diff: str) -> Tuple[str, dict]:
        sys_prompt = self.config.system_prompt or DEFAULT_SYSTEM_PROMPT
        user_prompt = build_user_prompt(
            diff,
            get_git_status(),
            infer_scope(get_changed_files()),
            self.config.custom_prompt,
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        data = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
        }

        try:
            resp = requests.post(
                self.api_url,
                json=data,
                timeout=self.config.timeout,
            )
        except requests.exceptions.Timeout:
            raise AITimeoutError("Ollama 请求超时") from None
        except requests.exceptions.ConnectionError:
            raise AITimeoutError(
                f"无法连接 Ollama 服务 ({self.config.ollama_host})，请确保 Ollama 已启动"
            ) from None

        if resp.status_code != 200:
            raise AIResponseError(
                f"Ollama 请求失败 (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        try:
            body = resp.json()
        except ValueError:
            raise AIResponseError(f"Ollama 返回非 JSON 格式: {resp.text[:200]}") from None

        try:
            content = body["message"]["content"]
        except (KeyError, TypeError):
            raise AIResponseError(
                f"Ollama 返回格式异常: {str(body)[:300]}"
            ) from None

        prompt_eval = body.get("prompt_eval_count", 0)
        eval_count = body.get("eval_count", 0)
        usage = {
            "prompt_tokens": prompt_eval,
            "completion_tokens": eval_count,
            "total_tokens": prompt_eval + eval_count,
        }
        return content.strip(), usage


def create_provider(config: Config):
    """Factory: create the appropriate AI provider."""
    if config.provider == "ollama":
        return OllamaProvider(config)
    return OpenAIProvider(config)


# ── Core Logic ─────────────────────────────────────────────────────────
def generate_commit_message(
    diff: str, config: Config
) -> Tuple[str, dict]:
    """Generate a commit message via AI."""
    diff = _truncate_diff(diff)
    provider = create_provider(config)
    return provider.generate(diff)


# ── Interactive Mode ───────────────────────────────────────────────────
def confirm_and_commit(message: str) -> None:
    """Interactive confirmation and commit flow."""
    print("\n" + "━" * 50)
    print("建议的提交信息:")
    print("━" * 50)
    print(message)
    print("━" * 50 + "\n")

    while True:
        print("  [y] 确认提交  [e] 编辑后提交  [n] 取消")
        choice = input("选择 (y/e/n): ").strip().lower()

        if choice == "y":
            git_commit(message)
            break
        elif choice == "e":
            print("\n编辑提交信息 (可直接按 Enter 取消):")
            edited = input("> ").strip()
            if not edited:
                print("已取消。")
                break
            print(f"\n修改后:\n\n{edited}\n")
            confirm = input("确认提交? (y/n): ").strip().lower()
            if confirm == "y":
                git_commit(edited)
            else:
                print("已取消。")
            break
        elif choice == "n":
            print("已取消。")
            break


# ── CLI ────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Git-Commit-Sage 🤖 — AI 驱动的 Git 提交助手",
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

    logger.debug("Provider: %s | Model: %s | URL: %s", config.provider, config.model, config.api_url)

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
            logger.warning("暂存区为空，请先 git add 文件，或使用 -a 自动添加")
        else:
            logger.warning("未检测到未暂存的代码改动")
        sys.exit(0)

    # -- Generate commit message ------------------------------------------
    if not config.quiet:
        logger.info("AI 正在分析代码改动...")

    try:
        message, usage = generate_commit_message(diff, config)
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

    confirm_and_commit(message)


if __name__ == "__main__":
    main()
