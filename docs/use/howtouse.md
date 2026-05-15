# Restater 使用说明

## 运行

`.env` 中设置了 `RESTATER_DEFAULT_PROJECT_PATH`，可以省略项目路径：

```powershell
python -m restater check --note "项目初始说明"
```


## 输出

默认输出目录为：

```text
<当前 Restater 工作目录>/.restater/runs/<run_id>/
```

其中 `report.md` 是最终检查报告，`state.json` 是结构化运行状态。
