# Code Review Agent

An **agentic AI code review service** that inspects pull request diffs, runs automated checks, and posts structured reviews to GitHub.

Built to demonstrate both **Gen AI agent patterns** (tool use, ReAct loop, structured output) and **software engineering** (API server, webhooks, diff parsing, CLI, tests). Uses **Ollama** for local, private LLM inference.

## Architecture

```
┌─────────────┐     webhook      ┌──────────────────┐
│   GitHub    │ ───────────────► │  FastAPI Server  │
│  (PR event) │                  │  /webhook/github │
└─────────────┘                  └────────┬─────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
            ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
            │  Diff Parser │    │ Review Agent │    │ GitHub Client│
            │  (unified)   │    │ (ReAct loop) │    │ (post review)│
            └──────────────┘    └──────┬───────┘    └──────────────┘
                                       │
                              ┌────────┴────────┐
                              ▼                 ▼
                       ┌───────────┐    ┌──────────────┐
                       │ LLM Tools │    │  Analyzers   │
                       │ inspect   │    │  security    │
                       │ analyze   │    │  style       │
                       │ submit    │    │  test cov.   │
                       └───────────┘    └──────────────┘
```

### Agentic concepts

| Concept | Implementation |
|---------|----------------|
| **Tool use** | Agent calls `inspect_diff`, `analyze_file`, `check_security`, etc. |
| **ReAct loop** | Plan → act (tool) → observe → repeat until `submit_review` |
| **Structured output** | Final review as typed `ReviewSummary` with verdict + comments |
| **Human-in-the-loop** | Webhook triggers review; developer sees GitHub PR comments |
| **Fallback mode** | Offline static analysis when no API key is set |

### Software engineering

- **FastAPI** REST API + GitHub webhook handler
- **Pydantic** models for type-safe request/response
- **Unified diff parser** with language detection
- **Static analyzers** for security/style/test coverage heuristics
- **CLI** for local diff review
- **pytest** test suite

## Ollama setup

This project uses [Ollama](https://ollama.com) as the local LLM backend via its OpenAI-compatible API (`http://localhost:11434/v1`). No cloud API key is required.

**Recommended models** (good tool-calling support):

| Model | Pull command |
|-------|--------------|
| Llama 3.2 | `ollama pull llama3.2` |
| Qwen 2.5 | `ollama pull qwen2.5:7b` |
| Mistral | `ollama pull mistral` |
| Llama 3.1 | `ollama pull llama3.1` |

Set the model in `.env`:

```bash
OLLAMA_MODEL=qwen2.5:7b
```

If Ollama is not running, the agent falls back to **offline mode** (static analyzers only).

## Quick start

### 1. Install

```bash
cd llm-project
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -e ".[dev]"  # or: pip install -r requirements.txt
pip install pytest
```

### 2. Configure

```bash
cp .env.example .env
# Optional: edit .env to change OLLAMA_MODEL (default: llama3.2)
```

### 3. Review a local diff (offline — no API key needed)

```bash
python -m code_review_agent.cli review examples/sample.diff --offline
```

### 4. Start Ollama and pull a model

```bash
ollama serve          # if not already running
ollama pull llama3.2  # or: qwen2.5:7b, mistral, llama3.1
```

### 5. Review with the LLM agent

```bash
python -m code_review_agent.cli review examples/sample.diff -v
```

### 6. Start the webhook server

```bash
python -m code_review_agent.cli serve
# or: uvicorn code_review_agent.main:app --reload
```

## GitHub integration

### Webhook setup

1. Create a repo webhook pointing to `https://your-host/webhook/github`
2. Content type: `application/json`
3. Secret: match `GITHUB_WEBHOOK_SECRET` in `.env`
4. Events: **Pull requests**

On `opened`, `synchronize`, or `reopened`, the agent fetches the PR diff, runs the review, and posts a GitHub review.

### Review a PR from CLI

```bash
export GITHUB_TOKEN=ghp_...
python -m code_review_agent.cli pr owner repo 42 --post
```

## API

### `POST /review`

```json
{
  "diff": "diff --git a/...",
  "pr_context": {
    "owner": "org",
    "repo": "app",
    "number": 42,
    "title": "Add auth",
    "head_sha": "abc123"
  },
  "post_to_github": false
}
```

### `GET /health`

Returns service status and configuration flags.

## Agent tools

| Tool | Purpose |
|------|---------|
| `inspect_diff` | Overview of changed files and line counts |
| `analyze_file` | Full patch for a specific file |
| `check_security` | Hardcoded secrets, eval, pickle, shell injection |
| `check_style` | TODOs, debug prints, bare except |
| `check_test_coverage` | Source changes without matching test changes |
| `submit_review` | Final structured review (verdict, comments) |

## Project structure

```
src/code_review_agent/
├── agent/
│   ├── orchestrator.py   # ReAct loop with Ollama tool calling
│   ├── tools.py          # Tool registry + execution
│   └── prompts.py        # System prompt
├── review/
│   ├── diff_parser.py    # Unified diff parsing
│   ├── analyzers.py      # Static security/style checks
│   └── offline.py        # No-LLM review path
├── github/
│   └── client.py         # API client + webhook helpers
├── main.py               # FastAPI app
├── cli.py                # Typer CLI
├── models.py             # Pydantic schemas
└── config.py             # Settings from .env
```

## Run tests

```bash
pytest tests/ -v
```

## Roadmap ideas

- [ ] AST-based analysis (Python `ast`, TypeScript parser)
- [ ] LangGraph multi-agent: Security specialist + Performance specialist
- [ ] Review quality eval harness (golden diffs + expected findings)
- [ ] GitHub App (instead of PAT) with fine-grained permissions
- [ ] Inline review comments with precise line mapping for all file types

## License

MIT
