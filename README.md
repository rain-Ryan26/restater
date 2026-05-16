# Restater

Restater 是一个本地项目状态检查 Agent。Phase 1 使用 LangGraph 串起项目目录扫描、需求整理、文件与命令行证据检查、状态判断和报告生成流程。

当前版本的目标是先跑通本地闭环：输入一个项目路径和用户初始说明，输出 Markdown 检查报告和机器可读的运行状态文件。

# 声明 ！disclaimer！
本项目的可靠性以及尤其是安全性都会有实现的不完善的地方，比如提示词注入防御或者是命令行权限管理什么的。尽管本项目会有相关设计，但是，除非你是了解这个项目或者相关技术的开发者，请不要使用它，因为这只是一个练习项目，难免会有漏洞。

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
RESTATER_MODEL_TIMEOUT_SECONDS=120
RESTATER_INSPECTION_MAX_ITERATIONS=4
```

默认输出目录是：

```text
<当前 Restater 工作目录>/.restater/runs/<run_id>/
```

其中 `report.md` 是最终检查报告，`state.json` 是本轮运行的结构化状态。

运行时默认输出各 Graph 节点的开始和结束信息，用于定位当前停留阶段。需要关闭进度输出时追加 `--quiet`。每个节点完成后都会刷新 `state.json`，模型调用超时或返回异常时会记录到 `errors` 并尽量生成降级报告。检查阶段使用循环式 `inspect` 节点，每轮只规划并执行下一小批检查，再决定继续检查还是进入最终判断。

## 当前边界

Phase 1 不使用数据库，不做 RAG 或向量检索，不接入联网搜索，也不处理用户中期交互。PDF 读取先支持基础文本提取；扫描件、图片页和复杂表格后续再作为独立能力补充。

### 项目思路

作为一名计算机系学生，很不幸，我在某一门课的project中因为没有认真计算每个部分的分数，导致丢不少分。于是，做了这么一个小东西，一定程度上也能解决我的实际需求。

本项目的可靠性以及尤其是安全性都会有实现的不完善的地方，比如提示词注入防御或者是命令行权限管理什么的。尽管本项目会有相关设计，但是，除非你是了解这个项目或者相关技术的开发者，请不要使用它，因为这只是一个练习项目，难免会有漏洞。

也刚好接触LangGraph技术，练一下手
