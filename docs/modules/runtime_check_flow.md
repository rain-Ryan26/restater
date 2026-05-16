# Runtime Check Flow

## 入口

CLI 入口位于 `src/restater/cli.py`，`check` 命令读取 `.env` 后调用 `run_check`。默认开启阶段进度输出，`--quiet` 关闭输出。

## 图执行

`src/restater/graph/runner.py` 负责创建运行目录、初始化状态、执行 LangGraph，并在每个节点完成后刷新 `state.json`。图执行异常时，runner 会把当前状态和 `RunError(stage="runner")` 写入 `state.json`，再抛出带有部分状态路径的异常。

`src/restater/graph/builder.py` 负责组装节点顺序，并用进度包装器在节点开始和结束时回调 CLI。节点内部也会回调 trace 信息，用于展示当前正在读取的需求源、PDF 提取、文件搜索、shell 命令、模型调用输入规模和模型返回数量。当前阶段顺序为：

1. `collect_context`
2. `extract_requirements`
3. `plan_inspection`
4. `execute_inspection`
5. `judge_status`
6. `generate_report`

## 需求来源识别

`collect_context` 会扫描项目文件并识别可能的需求来源。需求来源识别只接受 `.pdf`、`.md`、`.txt`、`.docx`，并限制在以下场景：

- 路径目录段包含 `requirements`、`requirement`、`rubric`、`assignment`、`spec`、`specs`。
- 文件名是 `AGENT.md`、`AGENTS.md`、`README.md`。
- 文件名主干包含需求关键词，例如 `requirement`、`rubric`、`任务`、`要求`、`评分`、`提交`、`说明`。

普通目录名中的 `project` 不再触发需求来源识别，避免把项目目录下的机器码文本、临时数据和测试输入误送到模型需求抽取阶段。

## 模型调用降级

模型调用集中在 `src/restater/llm.py`。请求超时由 `RESTATER_MODEL_TIMEOUT_SECONDS` 控制，默认 120 秒。HTTP 错误、连接错误、响应超时和 API 返回 JSON 解析失败都会转换为带上下文的 `RuntimeError`。

`plan_inspection` 不再把完整 `context_index` 原样送入模型。该节点会优先保留 requirement、state、test、doc、code 类上下文，最多传入 50 条、每条摘要最多 300 字，并将模型输入上限收紧到 25K 字符，避免把低价值文件索引拖进规划阶段。

以下节点会捕获模型异常并记录 `RunError`：

- `extract_requirements`：降级为每个需求来源生成一个低置信度需求项。
- `plan_inspection`：降级为基于需求标题和类别的文件搜索计划。
- `judge_status`：降级为对仓库可验证需求标记 `unknown`。
- `generate_report`：降级为不含模型摘要的 Markdown 报告。

该策略保证模型不稳定时仍能生成报告和结构化状态，但降级报告的完成度判断只代表保守占位结果。
