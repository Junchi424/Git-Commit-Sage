"""AI providers for Git-Commit-Sage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple

import requests

from commit_sage.config import Config, DEFAULT_SYSTEM_PROMPT
from commit_sage.exceptions import (
    AIAuthError,
    AIResponseError,
    AITimeoutError,
)
from commit_sage.git_ops import get_changed_files, get_git_status, infer_scope
from commit_sage.utils import build_user_prompt


class BaseProvider(ABC):
    """Abstract base for AI providers."""

    def __init__(self, config: Config):
        self.config = config

    def generate(self, diff: str) -> Tuple[str, dict]:
        messages = self._build_messages(diff)
        url = self._get_url()
        headers = self._get_headers()
        data = self._build_data(messages)

        try:
            resp = requests.post(
                url, headers=headers, json=data, timeout=self.config.timeout
            )
        except requests.exceptions.Timeout:
            raise AITimeoutError(self._timeout_message()) from None
        except requests.exceptions.ConnectionError:
            raise AITimeoutError(self._connection_error_message()) from None

        self._handle_status(resp)
        body = self._parse_json(resp)
        content = self._extract_content(body)
        usage = self._extract_usage(body)
        return content.strip(), usage

    def _build_messages(self, diff: str) -> list:
        sys_prompt = self.config.system_prompt or DEFAULT_SYSTEM_PROMPT
        user_prompt = build_user_prompt(
            diff,
            get_git_status(),
            infer_scope(get_changed_files()),
            self.config.custom_prompt,
        )
        return [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_json(self, resp: requests.Response) -> dict:
        try:
            return resp.json()
        except ValueError:
            raise AIResponseError(
                f"返回非 JSON 格式: {resp.text[:200]}"
            ) from None

    @abstractmethod
    def _get_url(self) -> str: ...

    def _get_headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def _build_data(self, messages: list) -> dict:
        return {"model": self.config.model, "messages": messages}

    @abstractmethod
    def _extract_content(self, body: dict) -> str: ...

    @abstractmethod
    def _extract_usage(self, body: dict) -> dict: ...

    def _handle_status(self, resp: requests.Response) -> None:
        if resp.status_code != 200:
            raise AIResponseError(
                f"请求失败 (HTTP {resp.status_code})"
            )

    def _timeout_message(self) -> str:
        return "API 请求超时，请检查网络或 API 地址"

    def _connection_error_message(self) -> str:
        return "无法连接 API 服务器，请检查 API_URL 和网络"


class OpenAIProvider(BaseProvider):
    """OpenAI-compatible chat completions API."""

    def _get_url(self) -> str:
        return self.config.api_url

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def _extract_content(self, body: dict) -> str:
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AIResponseError(
                f"API 返回格式异常，缺少 choices[0].message.content: {str(body)[:300]}"
            ) from None

    def _extract_usage(self, body: dict) -> dict:
        return body.get(
            "usage",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    def _handle_status(self, resp: requests.Response) -> None:
        if resp.status_code == 401:
            raise AIAuthError("API Key 无效，请检查 API_KEY 配置")
        if resp.status_code == 402:
            raise AIAuthError("API 余额不足，请检查账户额度")
        if resp.status_code == 403:
            raise AIAuthError("API 访问被拒绝，请检查 API Key 权限")
        if resp.status_code == 429:
            raise AIResponseError("API 请求频率过高，请稍后重试")
        if resp.status_code >= 500:
            raise AIResponseError(
                f"API 服务器错误 (HTTP {resp.status_code})"
            )
        if resp.status_code != 200:
            raise AIResponseError(
                f"API 请求失败 (HTTP {resp.status_code})"
            )


class OllamaProvider(BaseProvider):
    """Ollama local LLM provider."""

    def _get_url(self) -> str:
        return f"{self.config.ollama_host}/api/chat"

    def _build_data(self, messages: list) -> dict:
        return {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
        }

    def _extract_content(self, body: dict) -> str:
        try:
            return body["message"]["content"]
        except (KeyError, TypeError):
            raise AIResponseError(
                f"Ollama 返回格式异常: {str(body)[:300]}"
            ) from None

    def _extract_usage(self, body: dict) -> dict:
        prompt_eval = body.get("prompt_eval_count", 0)
        eval_count = body.get("eval_count", 0)
        return {
            "prompt_tokens": prompt_eval,
            "completion_tokens": eval_count,
            "total_tokens": prompt_eval + eval_count,
        }

    def _connection_error_message(self) -> str:
        return (
            f"无法连接 Ollama 服务 ({self.config.ollama_host})，"
            "请确保 Ollama 已启动"
        )


def create_provider(config: Config):
    """Factory: create the appropriate AI provider."""
    if config.provider == "ollama":
        return OllamaProvider(config)
    return OpenAIProvider(config)
