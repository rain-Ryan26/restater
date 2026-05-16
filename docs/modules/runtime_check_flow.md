# Runtime Check Flow

## 入口

CLI 入口位于 `src/restater/cli.py`，`check` 命令读取 `.env` 后调用 `run_check`。默认开启阶段进度输出，`--quiet` 关闭输出。

## 图执行

`src/restater/graph/runner.py` 负责创建运行目录、初始化状态、执行 LangGraph，并在每个节点完成后刷新 `state.json`。图执行异常时，runner 会把当前状态和 `RunError(stage="runner")` 写入 `state.json`，再抛出带有部分状态路径的异常。

`src/restater/graph/builder.py` 负责组装节点顺序，并用进度包装器在节点开始和结束时回调 CLI。节点内部也会回调 trace 信息，用于展示当前正在读取的需求源、PDF 提取、文件搜索、shell 命令、模型调用输入规模和模型返回数量。当前阶段顺序为：

1. `collect_context`
2. `classify_requirement_sources`
3. `extract_requirements`
4. `curate_requirements`
5. `inspect`
6. `judge_status`
7. `generate_report`

`inspect` 是循环节点。每轮执行时，它会根据当前 `requirements`、项目上下文、既有 `evidence` 和最近的检查步骤，让模型判断证据是否已经足够进入 `judge_status`。如果不足，它只规划最多 3 个下一步检查并立即执行；执行结果写回 `evidence` 后再次进入 `inspect`。循环由 `RESTATER_INSPECTION_MAX_ITERATIONS` 限制，默认最多 10 轮。

检查步骤可以绑定多个 `target_requirement_ids`。执行结果会分别关联到全部目标需求，避免一个跨需求检查只为第一个需求留下证据。该规则适用于文件搜索、文本预览、PDF 提取和 shell 命令结果。

PDF 提取入口位于 `src/restater/tools/pdf.py`。该入口会屏蔽 `pypdf` 对可恢复 PDF 结构问题输出的 warning，例如损坏的 trailer、xref 修复和对象偏移重建日志，避免这些底层恢复信息淹没 CLI 阶段进度。无法读取 PDF 的真实异常仍会向上抛出，由调用节点记录到运行状态。

如果循环因为达到轮次上限而结束，`inspection_decision` 会记录“达到检查上限后进入判定”的说明，最终报告概览也会展示这条检查过程说明。该反馈表示报告可能仍有未覆盖证据，需要在下一轮提高规划质量或继续检查。

`judge_status` 在最终判定前会执行一次通用补充证据读取：对缺少直接证据的仓库可验证需求，根据需求标题、描述和 `context_index` 匹配可能相关的 state/test/doc/code 文件，并读取少量摘要作为补充 evidence。该步骤不写死项目类型或固定文件名，只作为最终判定前的上下文补强。

## 需求来源识别

`collect_context` 会扫描项目文件并识别可能的需求来源。需求来源识别只接受 `.pdf`、`.md`、`.txt`、`.docx`，并限制在以下场景：

- 路径目录段包含 `requirements`、`requirement`、`rubric`、`assignment`、`spec`、`specs`。
- 文件名是 `AGENT.md`、`AGENTS.md`、`README.md`。
- 文件名主干包含需求关键词，例如 `requirement`、`rubric`、`任务`、`要求`、`评分`、`提交`、`说明`。

普通目录名中的 `project` 不再触发需求来源识别，避免把项目目录下的机器码文本、临时数据和测试输入误送到模型需求抽取阶段。

## 模型调用降级

模型调用集中在 `src/restater/llm.py`。请求超时由 `RESTATER_MODEL_TIMEOUT_SECONDS` 控制，默认 120 秒。HTTP 错误、连接错误、响应超时和 API 返回 JSON 解析失败都会转换为带上下文的 `RuntimeError`。

`inspect` 不把完整 `context_index` 原样送入模型。该节点会优先保留 requirement、state、test、doc、code 类上下文，最多传入 50 条、每条摘要最多 300 字，并将模型输入上限收紧到 25K 字符，避免把低价值文件索引拖进规划阶段。`judge_status` 会额外接收面向判定排序的上下文摘要，优先保留 state/test/doc/code 材料。

以下节点会捕获模型异常并记录 `RunError`：

- `extract_requirements`：降级为每个需求来源生成一个低置信度需求项。
- `inspect`：降级为基于需求标题和类别的文件搜索步骤。
- `judge_status`：降级为对仓库可验证需求标记 `unknown`。
- `generate_report`：降级为不含模型摘要的 Markdown 报告。

fallback 检查步骤使用跨项目类型的文本文件范围，不只覆盖 Markdown 和常见应用源码，也覆盖脚本、配置、硬件源码和汇编/hex 资产，例如 `.ps1`、`.sh`、`.v`、`.sv`、`.xdc`、`.tcl`、`.asm`、`.hex`。需求标题和描述会先去除通用动词、连接词和类别词，再生成搜索关键词，避免 fallback 被 `implement`、`with`、`for` 这类低区分度词带偏。文件搜索结果按命中词数量和路径信号排序，优先暴露 `stage`、`status`、`test_report`、`coverage`、`regression`、`run` 等更可能承载验证证据的文件。

该策略保证模型不稳定时仍能生成报告和结构化状态，但降级报告的完成度判断只代表保守占位结果。
