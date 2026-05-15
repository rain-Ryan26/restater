# Restater

Restater is a local project status checking Agent. Phase 1 runs a LangGraph flow over a project directory, extracts local requirements, inspects files and command output, and writes a Markdown report plus machine-readable state.

## Phase 1 Usage

```powershell
python -m restater check E:\path\to\project --note "initial project note"
```

Environment variables are loaded from `.env` by default. The first model adapter targets DeepSeek-compatible chat completions:

```powershell
DEEPSEEK_API_KEY=...
DEEPSEEK_API_BASE=https://api.deepseek.com
RESTATER_MODEL=deepseek-v4-pro
```

The default output directory is `<project>/.restater/runs/<run_id>/`.

