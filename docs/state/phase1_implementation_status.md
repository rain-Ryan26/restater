# Phase 1 实现状态

## 当前状态

Phase 1 已建立本地项目检查 Agent 的最小实现骨架。代码包含 CLI、配置读取、DeepSeek-compatible 模型客户端、LangGraph 主流程、基础文件扫描、PDF 文本提取、PowerShell 命令执行、结构化状态模型和 Markdown 报告生成。

## 已实现范围

- 输入：`project_path` 和 `user_note`。
- 默认路径：支持通过 `RESTATER_DEFAULT_PROJECT_PATH` 省略命令行中的项目路径。
- 输出：`report.md` 和 `state.json`。
- Graph 节点：抓取上下文、整理需求、规划检查路径、执行检查、打状态、生成最终报告。
- 工具：filesystem、shell、pdf。
- 模型：通过 `DEEPSEEK_API_KEY`、`DEEPSEEK_API_BASE`、`RESTATER_MODEL` 调用 DeepSeek-compatible chat completion API。
- 可观测性：CLI 默认输出每个 Graph 节点的开始和结束；每个节点完成后刷新 `state.json`。
- 降级处理：需求抽取、检查计划、状态判断和报告摘要的模型调用失败时，记录 `RunError` 并尽量生成可读报告。
- 持久化：文件系统输出，不使用数据库。

## 未实现范围

- PostgreSQL。
- RAG 或向量检索。
- 联网搜索。
- 用户中期交互和弹窗提问。
- 非仓库产物要求清单。
- 项目补充说明文档。
- 完整 OCR、视觉识别和复杂 PDF 表格恢复。

## 下一步验证

需要用一个真实项目目录和有效 DeepSeek API key 运行端到端检查，观察需求抽取、检查计划、命令执行和完成度估算是否稳定。随后再决定是否收紧命令执行策略、补充测试命令识别规则，或调整报告结构。

## 本地验证记录

- Python 源码已通过内存语法编译检查。
- CLI 入口 `python -m restater --help` 可正常加载。
- LangGraph 可编译为 `CompiledStateGraph`。
- PowerShell shell tool 可执行简单命令并读取输出。
- JSON 解析工具可解析模型 JSON 输出。
- 使用临时项目和 fake model client 跑通离线端到端冒烟测试，能够生成 `report.md`、`state.json`，并得到完成度估算。

真实 DeepSeek API 调用已暴露过读响应超时问题；当前实现已补充超时错误包装、阶段进度输出和模型节点降级路径。
