"""Configuration management for Git-Commit-Sage."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from commit_sage.exceptions import ConfigError

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
    dry_run: bool = False
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
        env_path = Path(__file__).parent.parent / ".env"
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
