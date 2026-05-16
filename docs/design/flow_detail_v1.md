# 第一版项目检查流程

## 主流程

Restater 的核心流程按 Agent 节点推进。初始化可以保留在 runner 层；Agent 主流程从 `collect_context` 开始。

1. `collect_context`

   进入用户指定的 `project_path`，遍历项目目录。

   这个节点主要做以下事情：

   - 读取用户传入的 `user_note`，把它作为后续判断的背景信息。
   - 扫描项目文件，建立 `context_index`。
   - 对每个文件记录相对路径、文件类型、简短摘要和初始置信度。
   - 按路径、文件名、后缀和内容摘要对文件做初步分类。
   - 分类结果包括需求候选、代码、测试、普通文档、状态文档、产物和未知文件。
   - 对 PDF 做第一页或前几页的基础文本提取，形成摘要。
   - 把看起来可能和需求有关的文件放入 `requirement_sources`。
   - 记录一条扫描证据，说明扫描了多少文件、发现了多少候选需求资料。

   这个节点的重点是建立项目索引和候选资料池。它不负责判断项目完成度，也不负责给需求打状态。

2. `classify_requirement_sources`

   读取 `collect_context` 得到的 `requirement_sources`，对候选资料继续分类。

   这个节点主要做以下事情：

   - 读取候选资料的正文、摘要或 PDF 提取文本。
   - 判断每份资料在项目里的角色。
   - 把资料分为权威需求来源、路由线索、实现文档、状态或测试证据、低置信资料。
   - 识别 README、AGENT、目录索引这类文件是在指路，还是本身包含真实要求。
   - 识别 `docs/requirements`、课程 PDF、评分规则、测试规格、提交规则这类更可能产出真实需求的资料。
   - 保留每份资料的角色、理由、置信度和来源路径。

   这个节点的目标是把“文件像不像需求资料”和“文件能不能产出真实需求”分开。后续抽取需求时，优先使用权威需求来源；路由线索只用于辅助定位。

3. `extract_requirements`

   从已经分类过的权威需求来源中抽取候选需求。

   这个节点主要做以下事情：

   - 读取权威需求来源的文本内容。
   - 从课程要求、评分规则、测试规格、提交规则、验收说明中抽取具体需求项。
   - 为每条候选需求生成稳定 ID、标题、描述、来源路径、类别、仓库内是否可验证、置信度。
   - 区分功能要求、文档要求、测试要求、提交要求、质量要求和未知类别。
   - 把线下答辩、现场演示、人工确认事项标记为不可仓库内验证。
   - 把模型抽取失败、JSON 解析失败、文件读取失败记录到 `errors`。

   这个节点抽取的是“候选需求”。它不应该把源文件本身包装成需求，例如不应该生成 `Review requirement source README.md` 这种需求项。

4. `curate_requirements`

   对 `extract_requirements` 产出的候选需求做筛选、去重和归一化。

   这个节点主要做以下事情：

   - 删除由 README、AGENT、目录索引、测试报告索引误生成的假需求。
   - 合并多个来源里重复表达的需求。
   - 当 README 或 AGENT 与权威需求文档表达相同内容时，保留权威来源版本。
   - 修正需求类别，例如把提交目录要求归入 `submission`，把测试覆盖要求归入 `test`。
   - 修正 `verifiable_in_repo`，避免把现场汇报、视频外部提交等事项纳入仓库完成度分母。
   - 标记低置信需求，必要时把它们降级为不参与完成度的待确认项。
   - 形成最终进入检查阶段的 `requirements`。

   这个节点是需求进入检查阶段前的门槛。后面的检查、打状态和完成度计算只能使用这里确认后的需求清单。

5. `inspect`

   `inspect` 是循环节点。它围绕最终 `requirements` 规划并执行下一小批检查。

   每一轮 `inspect` 主要做以下事情：

   - 读取当前 `requirements`、`context_index`、已有 `evidence`、已有 `plan` 和 `errors`。
   - 判断当前证据是否已经足够进入 `judge_status`。
   - 如果证据不足，规划最多 3 个下一步检查动作。
   - 检查动作可以是搜索文件、读取文件、解析 PDF、运行安全命令、查看测试输出。
   - 每个动作需要绑定目标需求 ID，说明预期证据是什么。
   - 执行动作后，把结果写入 `evidence`。
   - 如果执行 shell 命令，记录命令、工作目录、退出码、stdout、stderr 和耗时。
   - 把本轮实际执行的动作追加到 `plan`。
   - 更新 `inspection_iteration`。

   `inspect` 的循环出口有三种：

   - 模型判断证据足够，进入 `judge_status`。
   - 没有新的检查动作可执行，进入 `judge_status`。
   - 达到最大检查轮数，进入 `judge_status`。

   如果仍有必要继续检查，并且没有达到最大轮数，流程回到 `inspect` 自身继续下一轮。

6. `judge_status`

   根据最终需求清单和检查证据给每个需求打状态。

   这个节点主要做以下事情：

   - 读取最终 `requirements` 和全部 `evidence`。
   - 对每个仓库可验证需求判断 `done`、`partial`、`missing` 或 `unknown`。
   - 为每个判断写出简短原因。
   - 关联支撑判断的 evidence ID。
   - 对不可仓库验证的需求给出说明，不把它们计入仓库完成度分母。
   - 如果模型判断失败，为缺失判断的需求补 `unknown`。
   - 计算 `completion_estimate`，包括完成度百分比、统计数量和估算依据。

   这个节点不重新抽取需求，也不重新扩大需求范围。它只对 `curate_requirements` 确认后的需求负责。

7. `generate_report`

   生成最终 Markdown 报告。

   这个节点主要做以下事情：

   - 读取项目路径、用户说明、最终需求、状态判断、证据、完成度和命令执行结果。
   - 生成报告总览，包括项目路径、完成度估算、估算依据和用户初始说明。
   - 生成状态汇总，包括已完成、部分完成、未完成、不确定、排除项数量。
   - 生成总体判断，说明主要风险、需求来源可靠性和下一步重点。
   - 按状态分组输出需求项。
   - 每个需求项输出需求源、检查主题、判断原因和证据摘要。
   - 输出命令执行摘要。
   - 输出下一步建议。
   - 把报告写入 `report.md`，并把路径写回 state。

   报告需要直接记录检查结论。需求来源不可靠、需求抽取失败、PDF 未可靠解析、完成度不可信等问题要在报告中明确写出。

## 循环结构

主流程中只有 `inspect` 是循环节点。

流程顺序是：

1. `collect_context`
2. `classify_requirement_sources`
3. `extract_requirements`
4. `curate_requirements`
5. `inspect`
6. 如果 `inspect` 判断需要继续检查，回到 `inspect`
7. 如果 `inspect` 判断可以结束检查，进入 `judge_status`
8. `generate_report`

## 当前实现与目标流程差异

当前代码已经实现：

1. `collect_context`
2. `extract_requirements`
3. `inspect`
4. `judge_status`
5. `generate_report`

目标流程需要补充：

1. `classify_requirement_sources`
2. `curate_requirements`

当前误判的核心原因是缺少这两个筛选节点。`collect_context` 把 README、AGENT、目录索引、测试报告索引放进候选池后，`extract_requirements` 一旦失败就会把每个候选文件 fallback 成一个需求项，后续 `inspect` 和 `judge_status` 会默认这些需求成立。

目标流程中，`classify_requirement_sources` 先判断资料角色，`curate_requirements` 再决定哪些候选需求能进入最终需求清单。这样 README、AGENT、索引文档可以继续作为路由线索或证据，但不会直接进入完成度计算。
