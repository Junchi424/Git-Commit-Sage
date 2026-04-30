# Git-Commit-Sage 🤖

AI 驱动的 Git 提交助手 — 自动分析代码改动，生成符合 [Conventional Commits](https://www.conventionalcommits.org/) 规范的提交信息。

## 功能

- **多 AI 提供商**: 支持 OpenAI、DeepSeek、Ollama，以及任意 OpenAI 兼容 API
- **Conventional Commits**: 自动生成 `feat:`, `fix:`, `chore:` 等规范格式，含类型校验
- **智能 Scope 推断**: 根据变更文件路径自动推断 commit scope
- **灵活交互**: 确认提交 / 编辑后提交 / 仅预览
- **Token 统计**: 显示每次 API 调用的 token 用量
- **安全**: API Key 通过 `.env` 管理，不硬编码
- **可安装**: 支持 `pip install` 作为全局命令使用

## 安装

### 方式 1: 直接使用

```bash
pip install -r requirements.txt
```

### 方式 2: 作为命令安装

```bash
pip install -e .
```

安装后可直接使用 `commit-sage` 命令。

## 配置

```bash
cp .env.example .env
```

编辑 `.env`:

```ini
API_KEY=sk-your-api-key-here
PROVIDER=openai      # openai / deepseek / ollama
# API_URL=https://api.openai.com/v1/chat/completions  # 可选，留空用默认
# MODEL=gpt-4o-mini  # 可选，留空用默认
```

## 支持的提供商

| 提供商 | 默认模型 | 默认 API 地址 |
|--------|----------|--------------|
| OpenAI | `gpt-4o-mini` | `https://api.openai.com/v1/chat/completions` |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/v1/chat/completions` |
| Ollama | `llama3` | `http://localhost:11434/api/chat` |
| 自定义 | 需指定 `--url` 和 `--model` | 任意兼容接口 |

### Ollama 使用

```bash
# 先拉取模型
ollama pull llama3

# 使用
python commit_sage.py --provider ollama --model llama3
```

## 使用方法

```bash
# 基本用法
python commit_sage.py                          # 分析暂存区 (git diff --cached)
python commit_sage.py -a                       # 自动 git add 全部改动再分析
python commit_sage.py --diff                   # 分析未暂存改动 (仅预览)
python commit_sage.py -p                       # 仅预览 AI 建议，不提交
python commit_sage.py -q                       # 静默模式，只输出提交信息

# 切换提供商
python commit_sage.py --provider deepseek
python commit_sage.py --provider ollama --model llama3

# 自定义 prompt
python commit_sage.py --prompt "请用英文写一个简洁的 commit message"
python commit_sage.py --system-prompt "你是一个严格的 code reviewer..."

# 完整示例
python commit_sage.py --provider openai --model gpt-4o -p
```

## 命令行参数

### Git 选项
| 参数 | 说明 |
|------|------|
| `-a, --all` | 自动执行 `git add -A` 后再分析 |
| `--diff` | 分析未暂存改动（`git diff`） |

### AI 选项
| 参数 | 说明 |
|------|------|
| `--provider` | AI 提供商：`openai` / `deepseek` / `ollama` |
| `-m, --model` | 指定模型名称 |
| `--url` | 自定义 API 地址 |
| `--prompt` | 自定义用户 prompt |
| `--system-prompt` | 自定义系统 prompt（也可设 `SYSTEM_PROMPT` 环境变量） |
| `--timeout` | API 超时秒数（默认 60） |
| `--ollama-host` | Ollama 服务地址（默认 `http://localhost:11434`） |

### 输出选项
| 参数 | 说明 |
|------|------|
| `-p, --preview` | 仅显示 AI 建议，不提交 |
| `-q, --quiet` | 静默模式，仅输出提交信息到 stdout |
| `-v, --verbose` | 详细输出调试信息 |

## 运行测试

```bash
pip install pytest pytest-mock
pytest tests/ -v
```

## 项目结构

```
├── commit_sage.py       主程序
├── pyproject.toml       项目配置 & 打包
├── tests/
│   └── test_commit_sage.py  单元测试
├── requirements.txt     依赖
├── .env.example         配置示例
├── .gitignore           Git 忽略规则
└── README.md
```
