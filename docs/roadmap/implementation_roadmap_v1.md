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
- `output_dir`：报告和运行状态输出目录，默认可以是当前项目下的 `.restater/runs/<run_id>/`。

模型相关环境变量：

- `DEEPSEEK_API_KEY`：DeepSeek API key，也可用 `RESTATER_API_KEY` 作为通用别名。
- `DEEPSEEK_API_BASE`：DeepSeek-compatible API base URL，默认 `https://api.deepseek.com`。
- `RESTATER_MODEL`：模型名，默认 `deepseek-v4-pro`。
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
