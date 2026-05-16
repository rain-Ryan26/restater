# Restater 使用说明

## 运行

.\.venv\Scripts\Activate.ps1

`.env` 中设置了 `RESTATER_DEFAULT_PROJECT_PATH`，可以省略项目路径：


python -m restater check --note "你来整理一下这个项目的进度"
想要安静输出的时候使用   --quiet

默认输出阶段进度和关键子步骤：

```text
[restater] start collect_context
[restater]   - scan project: E:\path\to\project
[restater]   - scanned files=97, requirement_sources=8
[restater] done  collect_context (0.1s)

[restater] start extract_requirements
[restater]   - read requirement sources: 8
[restater]   - model call: requirement extraction, input_chars=30000
```

模型节点会输出可展示的 `model summary`、输入规模和返回数量；工具节点会输出 PDF 提取、文件搜索、文本预览和 shell 命令执行。隐藏推理链不写入终端，终端只展示模型返回的摘要和可复核的执行信息。

## 输出

默认输出目录为：

```text
<当前 Restater 工作目录>/.restater/runs/<run_id>/
```

其中 `report.md` 是最终检查报告，`state.json` 是结构化运行状态。
