# Runtime Check Flow

## 入口

CLI 入口位于 `src/restater/cli.py`，`check` 命令读取 `.env` 后调用 `run_check`。默认开启阶段进度输出，`--quiet` 关闭输出。

## 图执行

`src/restater/graph/runner.py` 负责创建运行目录、初始化状态、执行 LangGraph，并在每个节点完成后刷新 `state.json`。图执行异常时，runner 会把当前状态和 `RunError(stage="runner")` 写入 `state.json`，再抛出带有部分状态路径的异常。

`src/restater/graph/builder.py` 负责组装节点顺序，并用进度包装器在节点开始和结束时回调 CLI。当前阶段顺序为：

1. `collect_context`
2. `extract_requirements`
3. `plan_inspection`
4. `execute_inspection`
5. `judge_status`
6. `generate_report`

## 模型调用降级

模型调用集中在 `src/restater/llm.py`。请求超时由 `RESTATER_MODEL_TIMEOUT_SECONDS` 控制，默认 120 秒。HTTP 错误、连接错误、响应超时和 API 返回 JSON 解析失败都会转换为带上下文的 `RuntimeError`。

以下节点会捕获模型异常并记录 `RunError`：

- `extract_requirements`：降级为每个需求来源生成一个低置信度需求项。
- `plan_inspection`：降级为基于需求标题和类别的文件搜索计划。
- `judge_status`：降级为对仓库可验证需求标记 `unknown`。
- `generate_report`：降级为不含模型摘要的 Markdown 报告。

该策略保证模型不稳定时仍能生成报告和结构化状态，但降级报告的完成度判断只代表保守占位结果。
