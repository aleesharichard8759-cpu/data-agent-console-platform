# Data Agent Console 产品级验收清单：阶段 8

## 1. 验收目标

本文用于验收 Data Agent Console 从产品定位、信息架构、领域模型、页面设计、前端 MVP 到 API 契约的阶段性完整性。

验收对象包括：

- 产品设计文档：`docs/product/00` 到 `docs/product/05`。
- 领域模型与配置 Schema：`docs/product/02-domain-model.md` 与 `docs/product/config-schemas/`。
- 前端 MVP：`console/`。
- API 契约：`docs/api/openapi.yaml` 与 `docs/api/api-design.md`。

验收结论分为：

| 状态 | 含义 |
|---|---|
| `通过` | 产品设计、MVP 展示和 API 契约已能支撑该验收项 |
| `部分通过` | 设计已覆盖，但前端、API 或真实集成仍有缺口 |
| `未通过` | 核心设计或演示能力缺失 |

## 2. 总体验收结论

| 验收维度 | 当前完成情况 |
|---|---|
| 产品定位是否清晰 | 通过 |
| Runtime 和 Data&QA Product 职责是否分离 | 通过 |
| Data&QA Product 是否不能绕过 Runtime | 通过 |
| 是否支持数据源、工具、策略、DLP、审计配置 | 部分通过 |
| 是否支持语义层、任务类型、澄清模板、分析工作流配置 | 部分通过 |
| 是否支持 Case / Eval / Trace / Bad Case 闭环 | 部分通过 |
| 是否支持环境、版本、发布、回滚 | 部分通过 |
| 是否支持权限、审批、审计 | 部分通过 |
| 是否支持 MVP 演示路径 | 通过 |
| 是否具备后续接真实 API 的扩展能力 | 通过 |

总体判断：

> 当前 Data Agent Console 已具备产品级 MVP 骨架，可以用于内部评审、演示和 API 评审；但还不能视为生产可用系统。下一阶段应优先补齐 mock API server、发布与环境管理页面、强类型 API schema、权限审批状态机和真实后端集成。

## 3. 分项验收清单

### 3.1 产品定位是否清晰

| 项 | 内容 |
|---|---|
| 验收方式 | Review `docs/product/00-product-positioning.md`，检查是否明确 Console 不是聊天窗口、不是直连 BI，而是配置、运营、观测、评测、发布和审计平台 |
| 通过标准 | 能用一句话说明产品定位；能说明目标用户、核心场景、非目标范围；能区分 Runtime 与 Data&QA Product 两个产品 |
| 当前完成情况 | 通过。阶段 0 已明确 Console 定位为两个 Agent 产品的配置中心、运营中心、观测中心、评测中心、发布中心和审计中心 |
| 风险 | 后续如果直接围绕聊天体验开发，容易偏离配置平台定位 |
| 后续改进建议 | 在前端首页增加“当前能力范围 / 非目标范围”只读说明；在 PRD 中继续保留“不是直接连库问数页”的边界说明 |

### 3.2 Runtime 和 Data&QA Product 职责是否分离

| 项 | 内容 |
|---|---|
| 验收方式 | Review `00-product-positioning.md`、`02-domain-model.md`、`03-runtime-pages.md`、`04-data-qa-product-pages.md`，检查职责边界和对象归属 |
| 通过标准 | Runtime 负责 Policy、DataTool、SQL Gateway、DLP、Audit、审批和发布门禁；Data&QA Product 负责问题理解、口径对齐、语义层、澄清、分析流程、答案模板和反馈 |
| 当前完成情况 | 通过。领域模型按 Runtime 侧和 Data&QA Product 侧拆分，页面设计也分为 Runtime 配置中心和 Data&QA 产品配置 |
| 风险 | 后续实现时如果为了开发方便把策略、语义层、工具路由混在同一配置对象里，会造成职责边界退化 |
| 后续改进建议 | 后端实现时按 `/runtime/*` 和 `/product/*` 分层；数据库表或配置 store 也保持 Runtime 配置对象和 Product 配置对象分区 |

### 3.3 Data&QA Product 是否不能绕过 Runtime

| 项 | 内容 |
|---|---|
| 验收方式 | Review 产品原则、领域模型、前端 guardrail 文案和 API 契约，检查是否禁止 Data&QA 直接携带数据库连接、凭证或直接执行 SQL |
| 通过标准 | Data&QA Product 只能引用 Runtime 已发布对象，例如 `runtime_environment_id`、`runtime_release_id`、`runtime_data_source_ids`、`runtime_data_tool_ids`；API 禁止明文 secret 和直连数据库信息 |
| 当前完成情况 | 通过。`docs/api/openapi.yaml` 已将 ProductResource 设计为引用 Runtime 对象；`docs/api/api-design.md` 明确 `RUNTIME_BOUNDARY_VIOLATION` 与 `SECRET_PLAINTEXT_FORBIDDEN` |
| 风险 | 前端 MVP 目前是本地 mock state，尚未通过真实接口校验请求体，因此只能证明产品和契约边界，不能证明运行时强制执行 |
| 后续改进建议 | 在 mock API server 中加入请求体敏感字段扫描；对 Product API 增加单元测试，覆盖 `password`、`token`、`connection_string`、裸 SQL 直连信息被拒绝 |

### 3.4 是否支持数据源、工具、策略、DLP、审计配置

| 项 | 内容 |
|---|---|
| 验收方式 | Review `03-runtime-pages.md`、`02-domain-model.md`、`openapi.yaml` 和前端 MVP 页面 |
| 通过标准 | 至少支持 Connector / DataSource、DataTool Registry、Policy Engine、SQL Gateway、DLP / Masking、Audit 的列表、详情或配置入口；高风险配置具备审批、版本和回滚 API |
| 当前完成情况 | 部分通过。文档和 API 覆盖完整；前端 MVP 已实现 Connector / DataSource、DataTool Registry、Policy Engine、SQL Gateway、Trace / Audit Logs 页面；但前端暂未单独实现 DLP / Masking 页面，Audit 以 Trace / Audit Logs 合并展示 |
| 风险 | DLP / Masking 如果只在文档里存在，演示时安全合规人员可能认为脱敏配置能力不足 |
| 后续改进建议 | 下一版前端补 `DLP / Masking` 独立页面；Audit 页面拆出策略裁决、SQL 审查、DLP 命中、审批记录四类筛选；API schema 进一步拆成 `Connector`、`DataSource`、`DataTool`、`Policy` 等强类型对象 |

### 3.5 是否支持语义层、任务类型、澄清模板、分析工作流配置

| 项 | 内容 |
|---|---|
| 验收方式 | Review `04-data-qa-product-pages.md`、`02-domain-model.md`、`openapi.yaml` 和前端 MVP |
| 通过标准 | 能配置 Agent App、任务类型、SemanticMetric、SemanticDimension、BusinessEntity、ClarificationTemplate、AnalysisWorkflow、AnswerTemplate，且体现“先理解、先对口径、再执行、再回答” |
| 当前完成情况 | 部分通过。产品文档和 API 覆盖完整；前端 MVP 已实现 Data&QA Agent Apps、Semantic Layer、Analysis Workflow 页面；任务类型、澄清模板、回答模板在文档和 API 中已定义，但前端尚未拆成独立页面 |
| 风险 | 如果任务类型和澄清模板只通过工作流间接配置，产品经理难以独立运营“先澄清再执行”的规则 |
| 后续改进建议 | 下一版前端补 `Task Types`、`Clarification Templates`、`Answer Templates` 页面；在 Analysis Workflow 页面增加步骤级校验，禁止执行步骤早于口径确认步骤 |

### 3.6 是否支持 Case / Eval / Trace / Bad Case 闭环

| 项 | 内容 |
|---|---|
| 验收方式 | Review `05-eval-observability-pages.md`、前端 Case Library / Eval Runs / Trace 页面和 API 的 `case-items`、`eval-runs`、`feedback-items` |
| 通过标准 | Case 可沉淀问题与期望行为；Eval Run 可选择 Agent 版本、Runtime 版本和 Case 集；Trace 可关联 Runtime Audit、Langfuse 和用户反馈；Bad Case 可归因、修复、转回归 Case、重跑 Eval、发布验证 |
| 当前完成情况 | 部分通过。文档完整覆盖闭环，前端 MVP 已实现 Case Library、Eval Runs、Trace / Audit Logs；API 覆盖 `case-items`、`eval-runs`、`feedback-items` 和 feedback triage；但前端尚未实现独立 Bad Case 工作台和评分规则页面 |
| 风险 | 没有 Bad Case 独立工作台时，线上反馈到修复上线的责任流可能不清晰 |
| 后续改进建议 | 增加 `Bad Case Workbench` 和 `Score Rules` 页面；在 API 中补充 Bad Case 专用视图或以 `case_type=bad_case` 的 CaseItem 强化查询；对 Langfuse 接入保持 `待确认` 状态，不让外部 score 成为唯一发布门禁 |

### 3.7 是否支持环境、版本、发布、回滚

| 项 | 内容 |
|---|---|
| 验收方式 | Review `01-information-architecture.md`、`02-domain-model.md`、`openapi.yaml` 和前端 MVP 的环境切换、版本展示 |
| 通过标准 | 支持 Environment、RuntimeRelease、ProductRelease；配置对象具备 version；高风险资源具备 rollback API；前端能展示环境和版本 |
| 当前完成情况 | 部分通过。领域模型和 API 已覆盖 environments、runtime-releases、product-releases、rollback；前端 MVP 顶部有环境切换和版本展示；但尚未输出专门的发布与环境管理页面文档，也未实现发布单、灰度、门禁、回滚详情页面 |
| 风险 | 发布中心缺失会让配置平台停留在“编辑配置”，不能完整证明“可发布、可回滚、可运营” |
| 后续改进建议 | 补 `docs/product/06-release-environment-pages.md`；前端新增 Release & Environment 页面；API 细化 ReleaseOrder、ReleaseGateResult、RolloutPolicy 和 RollbackRecord |

### 3.8 是否支持权限、审批、审计

| 项 | 内容 |
|---|---|
| 验收方式 | Review `03-runtime-pages.md`、`api-design.md`、`openapi.yaml`，检查 RBAC / ABAC、审批动作、审计响应字段和错误码 |
| 通过标准 | 所有写操作支持 `version`、`created_by`、`updated_by`、`approval_status`；高风险配置支持 `submit-for-approval`、`approve`、`reject`、`rollback`；所有响应包含 `trace_id` 和 `audit_refs`；权限错误码清晰 |
| 当前完成情况 | 部分通过。API 契约已经覆盖权限模型、审批动作、错误码和审计响应；产品文档明确最小权限、默认拒绝、按需授权、全程审计；前端 MVP 仅展示审批和审计样例，尚未实现真实权限控制 |
| 风险 | 真实实现若缺少后端权限中间件，前端展示无法阻止越权操作 |
| 后续改进建议 | 后端 mock API 先实现最小 RBAC；生产实现再接 SSO/IAM；增加审批状态机测试，覆盖审批中禁止 patch、G5 默认拒绝、无权限返回 `PERMISSION_DENIED` |

### 3.9 是否支持 MVP 演示路径

| 项 | 内容 |
|---|---|
| 验收方式 | 运行前端 `console/`，按左侧导航演示 Dashboard、Runtime 配置、Data&QA 配置、Case / Eval、Trace / Audit；打开新增 / 编辑弹窗并保存 mock state |
| 通过标准 | 12 个 MVP 页面可跳转；每页有表格或表单、示例数据、可打开关闭弹窗；环境切换可操作；新增或编辑能保存到本地 mock state；lint、typecheck、test、build 通过 |
| 当前完成情况 | 通过。前端 MVP 已实现 12 个页面，验证命令 `npm run lint`、`npm run typecheck`、`npm run test`、`npm run build` 均已通过 |
| 风险 | 当前是 mock state，不接真实 API；刷新页面后状态不会持久化 |
| 后续改进建议 | 建立 mock API server 后将前端数据源从本地 state 切到 REST API；增加 Playwright 冒烟脚本验证关键演示路径 |

### 3.10 是否具备后续接真实 API 的扩展能力

| 项 | 内容 |
|---|---|
| 验收方式 | Review `docs/api/openapi.yaml`、前端数据结构和领域模型，检查资源命名、版本字段、审批动作、错误码和 Runtime 引用是否可扩展 |
| 通过标准 | OpenAPI 覆盖 Runtime 和 Product 24 类资源；资源路径 REST 化；支持分页、筛选、写入元数据、审批、回滚、错误码；前端 mock 数据能映射到 API 资源 |
| 当前完成情况 | 通过。OpenAPI 已覆盖 24 类资源和动作 API；前端 `mockData.ts` 使用的页面对象可迁移到 API 返回数据；API 设计保留通用 resource schema，便于先做 mock store 再逐步强类型化 |
| 风险 | 通用 schema 过于宽松，真实开发时可能导致字段约束不足 |
| 后续改进建议 | 下一阶段将 OpenAPI 通用 schema 拆成强类型 schema；生成 TypeScript API client；引入请求体校验、权限中间件、审计中间件和契约测试 |

## 4. MVP 演示路径验收脚本

### 4.1 平台管理员接入数据源并配置安全策略

| 步骤 | 页面 | 验收点 |
|---|---|---|
| 1 | Dashboard | 查看 Runtime 健康、待审批、DLP 命中和 Eval 通过率 |
| 2 | Connector / DataSource | 打开新增连接器弹窗，填写 `secret_ref`，验证无明文 secret |
| 3 | DataTool Registry | 注册 `query_rma_metric_sql`，设置只读和风险等级 |
| 4 | Policy Engine | 查看 ALLOW / ASK / DENY 策略，确认高风险为 ASK 或 DENY |
| 5 | SQL Gateway | 查看 DDL / DML、SELECT *、无 LIMIT 等拦截规则 |
| 6 | Trace / Audit Logs | 查看权限裁决、DLP 结果、Langfuse Trace ID 和审计摘要 |

通过标准：能够完整讲清“数据源 -> 工具 -> 策略 -> SQL Gateway -> DLP -> Audit”的 Runtime 安全链路。

### 4.2 数据产品经理配置 RMA 问数 Agent

| 步骤 | 页面 | 验收点 |
|---|---|---|
| 1 | Data&QA Agent Apps | 查看或新增 `RMA 问数助手`，确认绑定 Runtime 版本 |
| 2 | Semantic Layer | 新增或编辑 RMA 指标，例如客诉率、退货率 |
| 3 | Analysis Workflow | 查看“理解 -> 对齐口径 -> Runtime 取数 -> 回答”的流程 |
| 4 | Case Library | 查看黄金 Case、澄清 Case、红队 Case |
| 5 | Eval Runs | 查看 RMA release gate 通过率 |

通过标准：能够完整讲清“先理解、先对口径、再执行、再回答”，且 Data&QA 不直接访问数据库。

### 4.3 数据团队验证 Agent 是否可上线

| 步骤 | 页面 | 验收点 |
|---|---|---|
| 1 | Case Library | 选择 RMA Case 集，包含 golden、clarification、red_team |
| 2 | Eval Runs | 选择 Agent 版本、Runtime 版本、Case 集运行评测 |
| 3 | Trace / Audit Logs | 查看失败 Trace、权限裁决、DLP 结果和最终回答 |
| 4 | Case Library | 将失败样例沉淀为 bad_case 或 regression Case |
| 5 | Dashboard | 查看发布门禁和风险指标 |

通过标准：能够完整讲清“Case -> Eval -> Trace -> Bad Case -> Regression -> Release Gate”的质量闭环。

## 5. 风险总表

| 风险 | 影响 | 优先级 | 建议动作 |
|---|---|---|---|
| 前端仍是本地 mock state | 无法验证真实权限、审批、审计和持久化 | P0 | 实现 mock API server |
| 发布与环境管理尚未独立成页面 | 发布、灰度、回滚演示不完整 | P0 | 补阶段 6 文档和前端页面 |
| DLP / Masking 前端页面未独立实现 | 安全合规演示弱 | P1 | 从 Runtime 页面中拆出 DLP / Masking |
| 任务类型、澄清模板、回答模板未独立实现 | Data&QA 产品配置不够细 | P1 | 增加三个 Product 配置页面 |
| OpenAPI 通用 schema 偏宽 | 后续后端字段约束不足 | P1 | 拆强类型 schema 并生成客户端 |
| Langfuse / SSO / IAM / Secret Manager 接入待确认 | 真实观测、权限和密钥管理无法落地 | P1 | 在系统设置中增加接入状态和待确认清单 |
| Bad Case 工作台未独立实现 | 闭环运营责任不清 | P2 | 增加 Bad Case Workbench 和修复任务状态机 |

## 6. 后续阶段建议

1. 阶段 6：发布与环境管理页面设计
   - 输出 `docs/product/06-release-environment-pages.md`。
   - 覆盖 Environment、Draft、ReleaseOrder、ReleaseGate、Rollout、Rollback。

2. 阶段 7：前端 MVP 扩展
   - 新增 DLP / Masking、Task Types、Clarification Templates、Answer Templates、Release & Environment、Bad Case Workbench。

3. 阶段 9：Mock API Server
   - 基于 `docs/api/openapi.yaml` 实现 mock backend。
   - 前端从本地 mock state 切到 REST API。

4. 阶段 10：契约测试与权限测试
   - 增加 OpenAPI contract test。
   - 增加 secret 明文拒绝、Runtime 边界拒绝、审批状态机、默认拒绝测试。

## 7. 验收结论

当前阶段可以通过产品级 MVP 验收，但只适合进入内部评审和 mock 集成阶段，不适合直接进入生产集成。

必须先完成以下 P0 项，才能进入真实 API 集成：

- Mock API Server。
- 发布与环境管理页面。
- DLP / Masking 独立页面。
- 权限与审批状态机后端校验。
- OpenAPI 强类型 schema 拆分。
