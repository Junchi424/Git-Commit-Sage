"""Git-Commit-Sage — AI-powered Git commit message generator."""

from commit_sage.cli import build_parser, confirm_and_commit
from commit_sage.config import (
    CONVENTIONAL_COMMIT_TYPES,
    DEFAULT_SYSTEM_PROMPT,
    MAX_DIFF_CHARS,
    PROVIDER_DEFAULTS,
    Config,
    ConfigError,
)
from commit_sage.exceptions import (
    AIAuthError,
    AIError,
    AIResponseError,
    AITimeoutError,
    CommitSageError,
    GitError,
)
from commit_sage.git_ops import (
    _run_git,
    get_changed_files,
    get_git_diff,
    get_git_status,
    git_add_all,
    git_commit,
    infer_scope,
)
from commit_sage.main import main
from commit_sage.providers import (
    BaseProvider,
    OllamaProvider,
    OpenAIProvider,
    create_provider,
)
from commit_sage.utils import (
    _truncate_diff,
    build_user_prompt,
    display_usage,
    extract_first_line,
    validate_conventional_commit,
)
