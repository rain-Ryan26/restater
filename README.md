# Restater

Restater 是一个本地项目状态检查 Agent。Phase 1 使用 LangGraph 串起项目目录扫描、需求整理、文件与命令行证据检查、状态判断和报告生成流程。

当前版本的目标是先跑通本地闭环：输入一个项目路径和用户初始说明，输出 Markdown 检查报告和机器可读的运行状态文件。

## Phase 1 用法

```powershell
python -m restater check E:\path\to\project --note "项目初始说明"
```

如果 `.env` 中设置了默认项目路径，也可以省略路径：

```powershell
python -m restater check --note "项目初始说明"
```

默认会从 `.env` 读取模型配置。当前模型适配器按 DeepSeek-compatible chat completion API 设计：

```powershell
DEEPSEEK_API_KEY=...
DEEPSEEK_API_BASE=https://api.deepseek.com
RESTATER_MODEL=deepseek-v4-pro
RESTATER_DEFAULT_PROJECT_PATH=E:\D_C_tryings1\restaterplayground1
```

默认输出目录是：

```text
<当前 Restater 工作目录>/.restater/runs/<run_id>/
```

其中 `report.md` 是最终检查报告，`state.json` 是本轮运行的结构化状态。

## 当前边界

Phase 1 不使用数据库，不做 RAG 或向量检索，不接入联网搜索，也不处理用户中期交互。PDF 读取先支持基础文本提取；扫描件、图片页和复杂表格后续再作为独立能力补充。
