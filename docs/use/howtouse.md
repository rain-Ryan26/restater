# Restater 使用说明

## 运行

.\.venv\Scripts\Activate.ps1

`.env` 中设置了 `RESTATER_DEFAULT_PROJECT_PATH`，可以省略项目路径：


python -m restater check --note "你来整理一下这个项目的进度"
想要安静输出的时候使用   --quiet



## 输出

默认输出目录为：

```text
<当前 Restater 工作目录>/.restater/runs/<run_id>/
```

其中 `report.md` 是最终检查报告，`state.json` 是结构化运行状态。
