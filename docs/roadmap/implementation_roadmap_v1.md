# Restater 实现路线草案

## 总体方向

Restater 第一版先做成本地项目检查 Agent。核心输入是项目路径和用户首次文本说明；核心输出是项目检查报告。系统进入项目目录后自行识别需求来源、代码、测试、文档和提交材料，再通过 LangGraph 串起上下文抓取、需求整理、检查规划、执行检查、状态判断和报告生成。

第一版不引入数据库、不做 RAG、不做联网搜索，也不做复杂 UI。当前目标是把流程闭环跑通，并让每一步的状态、证据和报告结果可追踪。PostgreSQL、向量检索、用户中期交互、多 Agent 拆分和更强 PDF/OCR 能力放到后续阶段。

## 第一版技术取向

- 编程语言：Python。
- 流程框架：LangGraph。
- 模型接口：DeepSeek-compatible chat completion API。
- 状态模型：先用 Pydantic 或 TypedDict 表达，不落数据库。
- 持久化：先用文件系统保存运行产物，例如 `runs/<run_id>/state.json`、`report.md`、`artifacts/`。
- 本地操作：通过 PowerShell 命令执行、文件读取、目录扫描和文本搜索实现。
- PDF 读取：第一版先接基础 PDF 文本提取接口；图片型 PDF、扫描件和复杂表格先记录为能力缺口。

## 建议目录结构

```text
src/restater/
  __init__.py
  cli.py
  config.py
  graph/
    builder.py
    state.py
    nodes/
      collect_context.py
      extract_requirements.py
      plan_inspection.py
      execute_inspection.py
      judge_status.py
      generate_report.py
  models/
    context.py
    requirement.py
    plan.py
    evidence.py
    finding.py
    report.py
  tools/
    filesystem.py
    shell.py
    pdf.py
  services/
    project_scanner.py
    requirement_extractor.py
    report_renderer.py
  prompts/
    collect_context.md
    extract_requirements.md
    plan_inspection.md
    judge_status.md
    generate_report.md
```

目录拆分原则是：`graph/` 只放流程编排和节点；`models/` 放结构化数据；`tools/` 放底层能力；`services/` 放可测试的业务逻辑；`prompts/` 放节点提示词。这样后续加入数据库、RAG 或多 Agent 时，不需要重写主流程。

## 核心接口草案

### CLI 输入

第一版先提供命令行入口：

```bash
restater check <project_path> --note "<user_note>" --out <output_dir>
```

参数含义：

- `project_path`：被检查项目根目录。
- `user_note`：用户首次文本说明，可为空，但入口应保留该字段。
- `output_dir`：报告和运行状态输出目录，默认是当前 Restater 工作目录下的 `.restater/runs/<run_id>/`。
- 如果 `RESTATER_DEFAULT_PROJECT_PATH` 已配置，`project_path` 可以省略。

模型相关环境变量：

- `DEEPSEEK_API_KEY`：DeepSeek API key，也可用 `RESTATER_API_KEY` 作为通用别名。
- `DEEPSEEK_API_BASE`：DeepSeek-compatible API base URL，默认 `https://api.deepseek.com`。
- `RESTATER_MODEL`：模型名，默认 `deepseek-v4-pro`。
- `RESTATER_DEFAULT_PROJECT_PATH`：默认被检查项目目录，便于直接运行 `restater check --note ...`。
- `RESTATER_TEMPERATURE`、`RESTATER_MAX_TOKENS`：模型调用参数。

### Graph State

```python
class ProjectCheckState(TypedDict):
    run_id: str
    project_path: str
    user_note: str
    output_dir: str
    context_index: list[ContextItem]
    requirement_sources: list[RequirementSource]
    requirements: list[RequirementItem]
    plan: list[InspectionStep]
    evidence: list[EvidenceItem]
    findings: list[FindingItem]
    completion_estimate: CompletionEstimate | None
    report_path: str | None
    errors: list[RunError]
```

状态设计先保持扁平。每个节点只追加或更新自己负责的字段，避免把大量临时信息塞进单个字符串。

### 关键数据模型

```python
class ContextItem(BaseModel):
    path: str
    kind: Literal["requirement", "code", "test", "doc", "state", "artifact", "unknown"]
    summary: str
    confidence: float

class RequirementItem(BaseModel):
    id: str
    title: str
    description: str
    source_path: str
    category: Literal["function", "document", "test", "submission", "quality", "unknown"]
    verifiable_in_repo: bool

class InspectionStep(BaseModel):
    id: str
    target_requirement_ids: list[str]
    action: str
    expected_evidence: str
    tool_hint: Literal["filesystem", "shell", "pdf", "model"]

class EvidenceItem(BaseModel):
    id: str
    requirement_id: str | None
    source: Literal["file", "pdf", "shell", "model"]
    content_summary: str
    raw_ref: str | None

class FindingItem(BaseModel):
    requirement_id: str
    status: Literal["done", "partial", "missing", "unknown"]
    reason: str
    evidence_ids: list[str]
```

`verifiable_in_repo` 用于后续处理答辩、线下演示、讲解代码原理等非仓库产物要求。第一版可以识别但不纳入完成度判断，第二阶段再单独生成非仓库产物清单。

## Graph 节点实现思路

### collect_context

输入 `project_path` 和 `user_note`。扫描目录，读取轻量文本文件，初步提取 PDF 文本，标记需求来源、代码、测试、文档、状态文档和提交材料。该节点只建立上下文索引，不做最终判断。

### extract_requirements

读取被标记为需求来源的材料，生成结构化需求列表。输出的是 `requirements`，不是额外 checklist。需求项需要保留来源、分类和是否可在仓库内验证。

### plan_inspection

根据 `requirements` 和 `context_index` 生成检查计划。计划说明接下来查哪些文件、是否运行命令、每一步需要什么证据。第一版可以由一个模型节点完成，不强制拆多个 Agent。

### execute_inspection

按计划执行读取文件、搜索文本、运行 PowerShell 命令和读取 PDF 的动作。该节点负责收集证据，不直接给最终状态。

### judge_status

根据需求和证据打状态：`done`、`partial`、`missing`、`unknown`。同时生成完成度估算。第一版完成度可以采用简单权重：可验证需求中 `done=1`、`partial=0.5`、`missing/unknown=0`。

### generate_report

生成 Markdown 报告。报告包括完成度百分比、已完成项、部分完成项、未完成项、不确定项、关键证据、命令执行摘要、风险和下一步建议。写报告是节点动作，不单独抽象成业务 tool。

## Tool 边界

### shell tool

负责执行 PowerShell 命令并返回结构化结果：

```python
class ShellResult(BaseModel):
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
```

第一版只要求能跑命令并拿到终端反馈，不负责自动修复环境、不负责安装依赖、不负责复杂交互式命令。

### filesystem tool

负责列目录、读文本文件、搜索文本和记录文件摘要。中文和前端文件需要按严格 UTF-8 读取，写回统一 UTF-8 no BOM。

### pdf tool

负责把 PDF 转成可供模型处理的文本和页级摘要。第一版先做基础文本提取；后续再扩展 OCR、视觉识别、表格恢复和图片页理解。

## 阶段路线

### Phase 1：本地闭环

目标是跑通单项目检查流程。实现 CLI、LangGraph 主流程、文件扫描、基础 PDF 文本提取、PowerShell 命令执行、状态判断和 Markdown 报告。

验收标准：

- 输入项目路径和用户说明后可以生成报告。
- 报告能列出需求、状态、证据和完成度。
- 命令执行结果能进入证据链。
- 运行状态可以保存到本地文件。

### Phase 2：交互和边界补充

加入用户中期提问能力。当需求来源不完整、PDF 无法解析、项目说明不足或发现关键边界问题时，Agent 可以向用户提问。该阶段还生成项目补充说明文档，并单独维护非仓库产物要求清单。

### Phase 3：检索和长期记忆

评估是否引入 RAG 和向量检索。当前第一版没有明显强需求，后续只有在项目文档很大、跨项目复用要求明显、历史状态需要检索时再引入。实现上可以把向量库接在 `context_index` 和历史报告之上，而不是改写主流程。

### Phase 4：数据库和多项目管理

引入 PostgreSQL 保存项目、运行记录、需求项、证据和报告元数据。数据库只在需要多项目管理、历史对比、多人协作或 Web UI 时引入。第一版不使用数据库，避免为了存储结构拖慢流程验证。

## 当前决策

- 第一版优先验证流程，不做数据库。
- 第一版不做 RAG，不做向量检索。
- 第一版不做联网搜索。
- 第一版接 DeepSeek-compatible API，key 和模型名通过环境变量提供。
- 第一版 PDF 先做基础文本读取，复杂 PDF 能力独立为后续 tool。
- 第一版先用文件系统保存 state 和报告。
- LangGraph 是主流程核心，其他模块围绕它提供数据结构和工具能力。

## Inspect 链路校准

最近一次真实项目检查暴露出的问题不是上下文扫描完全失败，而是 `inspect` 没有稳定保存“已检查到哪里、还缺什么、哪些自动化验证已经尝试过”的过程状态。单纯提高循环上限不能解决该问题；10 轮循环仍然重复读取源码，说明流程缺少明确的思考输出、验证工具反馈和跳出条件。

后续修复保持项目类型无关，不把 CPU、汇编、前端、数据库等具体项目形态写成固定规则。模型仍然负责根据需求、上下文索引、既有证据和检查进度决定下一步；执行层提供更可靠的只读工具，尤其是自动化验证命令运行工具。

### Inspect 每轮决策要求

`inspect` 每轮进入工具执行前必须先输出结构化思考结果。该输出不是隐藏推理，而是可保存到 state 的开发者可读检查状态，至少包括：

- `coverage_summary`：当前已覆盖的需求、证据主题和验证结果。
- `missing_parts`：仍缺少直接证据的需求或能力点。
- `next_action_type`：下一步是读取文件、搜索文本、运行自动化验证、解析测试报告，还是结束 inspect。
- `automation_test_assessment`：当前项目是否存在可运行的自动化测试；如果存在，哪些命令值得尝试；如果没有发现或不适合运行，需要写明原因。
- `continue_or_finish`：继续 inspect 或输出 `inspect_over`，进入最终判定。

提示词不能再写成偏向 `filesystem search/read`。读取和搜索仍是基础能力，但自动化测试、构建、脚本验证和测试报告解析必须作为同等级证据入口。模型需要先判断证据缺口，再选择工具，而不是默认继续读源码。

### 只读验证运行工具

自动化验证不应做成固定 graph 节点。它应是 `inspect` 中途可以调用的 tool，名称可以暂定为 `run_validation_command` 或 `runtime_validation`。该工具只负责只读验证，不修改代码，不修复项目，不安装依赖，不执行破坏性命令。

工具职责：

- 从模型给出的候选命令、项目上下文和已发现文件中识别可运行的验证入口，例如 `pom.xml`、`package.json`、`pyproject.toml`、`pytest.ini`、`build.gradle`、`Makefile`、`.ps1`、`.bat`、文档中的测试命令。
- 将候选命令重新组装成结构化执行请求，包括 `cwd`、`executable`、`args`、`env`、`timeout` 和 `purpose`。
- 禁止模型直接拼接 `cd && ...`、重定向、管道、嵌套 `powershell -Command` 等脆弱命令形式。工作目录由工具参数控制，stdout/stderr 由工具捕获。
- 对常见验证输出做轻量解析，例如 Maven Surefire、pytest、npm test、Gradle test 的通过/失败摘要。
- 将执行结果以短摘要返回给 `inspect`，包括命令、退出码、是否成功、关键 stdout/stderr、测试报告路径、失败摘要和无法运行原因。

该工具不是状态判断节点。它只提供新的观察结果；是否继续、是否换工具、是否进入 `judge_status` 仍由 `inspect` 的结构化决策决定。

### Inspect 状态记忆

`state.json` 需要保存比原始 evidence 更明确的 inspect 进度，避免模型在下一轮不知道已经读过什么、跑过什么。建议新增或整理以下状态字段：

- `inspection_progress`：按主题记录覆盖情况，例如需求解析、源码入口、自动化测试、构建结果、测试报告、提交材料、文档证据。
- `inspected_refs`：已经读取或搜索过的文件、目录、关键词和命令。
- `validation_attempts`：已尝试的验证命令、退出码、失败原因和可复用结果摘要。
- `open_questions`：仍然缺证据的需求点。
- `stop_reason`：进入最终判定的原因，例如 `inspect_over`、验证足够、关键验证不可运行、达到保护性上限。

这些字段用于给下一轮 `inspect` 提供工作记忆，而不是只把最近 30 条 evidence 截断后再次交给模型。重复读取同一类文件应由状态自然避免，而不是靠事后硬性禁止。

### Inspect 跳出条件

`inspect` 的终止应由模型输出的结构化 `inspect_over` 或等价字段驱动。保护性轮次上限仍可保留，但只能作为异常兜底，不应成为正常完成路径。

正常跳出条件包括：

- 每个仓库可验证需求都有足够的源码、文档、测试或验证结果证据。
- 自动化测试已运行并返回可解释结果，或已经记录清楚为什么不能运行。
- 剩余缺口无法通过继续读取仓库材料显著改善，应该交给最终报告说明风险。
- 当前 evidence 与 `inspection_progress` 已足够支撑 `judge_status` 做保守判定。

如果验证命令未跑成功，报告必须保留“尝试过什么、为什么失败、失败影响哪些需求”的信息，不能把运行失败静默折叠成源码不充分。

### 短期修复顺序

1. 重写 `inspect_next` 提示词，去掉默认偏向 filesystem 的表达，要求每轮先输出覆盖情况、缺口、自动化测试可行性、下一步工具选择和是否 `inspect_over`。
2. 增加 inspect 进度状态，把已读文件、已搜关键词、已跑命令、验证结果和未覆盖需求写入 `state.json`。
3. 实现只读验证运行工具，先支持结构化执行 Maven、npm、pytest、Gradle 和文档中明确给出的 PowerShell 验证命令。
4. 调整 shell 执行层，验证工具不接受模型拼好的整段 shell 字符串，而是执行结构化命令；保留普通 PowerShell tool 作为后续辅助能力。
5. 让 `inspect` 消费验证工具反馈，并基于 `inspection_progress` 决定继续、换检查主题或输出 `inspect_over`。
6. 将真实失败案例抽成回归 fixture，重点覆盖“存在 Maven 测试但模型重复读源码”“验证命令被错误包装”“stderr 有错误但 exit code 被误判为成功”等情况。

暂不做的内容：

- 暂不把自动化验证做成固定 graph 节点。验证运行首先是 inspect 可调用的工具。
- 暂不新增复杂 evidence 类型。先保证模型能稳定拿到验证反馈、检查进度和缺口状态。
- 暂不为某一种项目类型加入固定完成度规则。项目类型识别服务于工具候选命令发现，不替代模型的检查决策。

## Phase 1 当前实现落点

当前代码已按该路线建立第一版骨架：

- `src/restater/cli.py`：命令行入口。
- `src/restater/config.py`：`.env` 加载和运行配置。
- `src/restater/llm.py`：DeepSeek-compatible HTTP 模型客户端。
- `src/restater/graph/`：LangGraph builder、state、runner 和六个节点。
- `src/restater/tools/`：filesystem、shell、pdf 三类基础工具。
- `src/restater/services/`：项目扫描和报告渲染。
- `src/restater/prompts/`：需求整理、检查规划、状态判断和报告摘要提示词。

该实现仍属于 Phase 1 骨架，重点是跑通流程。后续需要用真实课程项目和真实 DeepSeek key 做端到端校准，尤其是需求抽取质量、计划生成质量、命令执行范围和完成度估算规则。
