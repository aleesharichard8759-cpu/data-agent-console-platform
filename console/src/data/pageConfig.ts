import type { NavGroup, PageConfig, PageGuidance, UserJourney } from "../types";

export const navGroups: NavGroup[] = [
  {
    label: "常用",
    items: [
      { route: "runtime-workbench", label: "Runtime 工作台" },
      { route: "dataqa-workspace", label: "问数工作台" },
      { route: "case-library", label: "Case / Eval" },
      { route: "trace-audit", label: "Trace / Audit" }
    ]
  },
  {
    label: "首页总览",
    items: [{ route: "dashboard", label: "首页看板" }]
  },
  {
    label: "Runtime 配置中心",
    items: [
      { route: "runtime-overview", label: "Runtime 总览" },
      { route: "connectors", label: "连接器 / 数据源" },
      { route: "datatools", label: "DataTool 注册中心" },
      { route: "policy-engine", label: "策略引擎" },
      { route: "sql-gateway", label: "SQL 网关" },
      { route: "dlp-masking", label: "DLP / Masking" }
    ]
  },
  {
    label: "Data&QA 产品配置",
    items: [
      { route: "agent-apps", label: "Agent 应用" },
      { route: "semantic-layer", label: "语义层" },
      { route: "analysis-workflow", label: "分析工作流" }
    ]
  },
  {
    label: "Case / Eval 中心",
    items: [
      { route: "case-library", label: "Case 库" },
      { route: "eval-runs", label: "评测运行" },
      { route: "bad-case-workbench", label: "Bad Case 工作台" }
    ]
  },
  {
    label: "观测与审计中心",
    items: [
      { route: "trace-audit", label: "链路追踪 / 审计日志" },
      { route: "approval-center", label: "审批中心" },
      { route: "release-center", label: "发布中心" }
    ]
  }
];

export const routePaths = {
  dashboard: "/",
  "runtime-workbench": "/runtime/workbench",
  "dataqa-workspace": "/workspace/data-qa",
  "runtime-overview": "/runtime/overview",
  connectors: "/runtime/connectors",
  datatools: "/runtime/datatools",
  "policy-engine": "/runtime/policy-engine",
  "sql-gateway": "/runtime/sql-gateway",
  "dlp-masking": "/runtime/dlp-masking",
  "approval-center": "/operations/approvals",
  "agent-apps": "/dataqa/apps",
  "semantic-layer": "/dataqa/semantic-layer",
  "analysis-workflow": "/dataqa/workflows",
  "case-library": "/eval/cases",
  "eval-runs": "/eval/runs",
  "bad-case-workbench": "/eval/bad-cases",
  "trace-audit": "/observability/traces",
  "release-center": "/release/environments"
} as const;

export const userJourneys: UserJourney[] = [
  {
    id: "new-source",
    title: "接入一个新数据源",
    user: "平台管理员",
    role: "platform_admin",
    outcome: "完成只读 Connector、DataTool、Policy、SQL Gateway 的安全接入闭环。",
    primaryRoute: "connectors",
    steps: [
      { label: "创建只读连接器", route: "connectors", status: "current" },
      { label: "注册受控 DataTool", route: "datatools", status: "todo" },
      { label: "配置默认拒绝策略", route: "policy-engine", status: "todo" },
      { label: "设置 SQL 门禁", route: "sql-gateway", status: "todo" },
      { label: "看审计与异常", route: "trace-audit", status: "todo" }
    ]
  },
  {
    id: "rma-agent",
    title: "配置 RMA 问数 Agent",
    user: "数据产品经理",
    role: "data_product_manager",
    outcome: "把 RMA 问题理解、口径对齐、工具调用和回答模板串成可发布产品。",
    primaryRoute: "agent-apps",
    steps: [
      { label: "创建 Agent 应用", route: "agent-apps", status: "current" },
      { label: "维护指标和维度", route: "semantic-layer", status: "todo" },
      { label: "编排分析工作流", route: "analysis-workflow", status: "todo" },
      { label: "沉淀上线 Case", route: "case-library", status: "todo" },
      { label: "运行发布评测", route: "eval-runs", status: "todo" }
    ]
  },
  {
    id: "release-gate",
    title: "验证 Agent 能否上线",
    user: "数据团队",
    role: "data_team",
    outcome: "用 Case / Eval / Trace 验证准确性、安全性和 Bad Case 回归。",
    primaryRoute: "case-library",
    steps: [
      { label: "选择 Case 集", route: "case-library", status: "current" },
      { label: "运行 Eval Run", route: "eval-runs", status: "todo" },
      { label: "查看失败 Trace", route: "trace-audit", status: "todo" },
      { label: "修复配置对象", route: "semantic-layer", status: "todo" },
      { label: "回归后再发布", route: "eval-runs", status: "todo" }
    ]
  }
];

export const pageGuidance: Record<keyof typeof routePaths, PageGuidance> = {
  dashboard: {
    goal: "用三条主路径组织 Console，而不是让用户自己在表格里找入口。",
    primaryTask: "从首页选择一个任务路径，按步骤跳转到相关页面。",
    nextLabel: "从接入新数据源开始",
    nextRoute: "connectors"
  },
  "runtime-workbench": {
    goal: "直接使用 Runtime 验证安全链路和运行治理作业。",
    primaryTask: "输入 SQL、工具请求或治理任务，查看 Policy、SQL Gateway、DLP、Plan Mode 和 Audit。",
    nextLabel: "查看 Runtime 配置",
    nextRoute: "runtime-overview"
  },
  "dataqa-workspace": {
    goal: "面向业务用户使用 RMA 问数助手，而不是配置 Agent。",
    primaryTask: "输入业务问题，查看理解、澄清、执行计划、答案、Trace 和反馈闭环。",
    nextLabel: "查看 Agent 配置",
    nextRoute: "agent-apps"
  },
  "runtime-overview": {
    goal: "判断 Runtime 安全链路是否健康。",
    primaryTask: "先看服务、SQL 拦截、DLP 命中和待审批，再跳转到具体配置页处理。",
    nextLabel: "处理 Connector / DataSource",
    nextRoute: "connectors"
  },
  connectors: {
    goal: "接入受 Runtime 管控的数据资产入口。",
    primaryTask: "新增只读 Connector，填写 secret_ref，绑定环境，再测试连接和可用表。",
    nextLabel: "注册 DataTool",
    nextRoute: "datatools"
  },
  datatools: {
    goal: "把数据访问能力包装成 Agent 可调用的受控工具。",
    primaryTask: "定义工具意图、入参出参、风险等级、Plan Mode 和调用权限。",
    nextLabel: "配置 Policy Engine",
    nextRoute: "policy-engine"
  },
  "policy-engine": {
    goal: "决定谁在什么条件下可以调用什么工具和访问什么数据。",
    primaryTask: "按 RBAC / ABAC、数据域、敏感等级和行列权限配置 ALLOW / ASK / DENY。",
    nextLabel: "设置 SQL Gateway",
    nextRoute: "sql-gateway"
  },
  "sql-gateway": {
    goal: "在 SQL 执行前完成 Dry Run、Explain、扫描量和风险裁决。",
    primaryTask: "配置禁止 DDL/DML、限制 SELECT *、默认 LIMIT、超时和最大扫描量。",
    nextLabel: "配置 DLP / Masking",
    nextRoute: "dlp-masking"
  },
  "dlp-masking": {
    goal: "把敏感字段识别、动态脱敏和导出限制落到字段级规则。",
    primaryTask: "维护敏感标签、脱敏规则、展示层动态脱敏、导出限制和命中日志预览。",
    nextLabel: "去 Runtime Workbench 验证",
    nextRoute: "runtime-workbench"
  },
  "approval-center": {
    goal: "统一处理高风险 SQL、策略变更、发布和回滚审批。",
    primaryTask: "查看待我审批、我发起的、已驳回和已发布申请，明确风险原因和影响对象。",
    nextLabel: "查看发布中心",
    nextRoute: "release-center"
  },
  "agent-apps": {
    goal: "定义一个可发布的 Data&QA Agent 产品实例。",
    primaryTask: "配置目标用户、任务类型、Runtime 绑定、数据源绑定、语义层和工具集。",
    nextLabel: "维护 Semantic Layer",
    nextRoute: "semantic-layer"
  },
  "semantic-layer": {
    goal: "让 Agent 先对齐业务口径，再规划查询。",
    primaryTask: "维护指标、维度、实体、同义词、时间口径、过滤条件和字段映射。",
    nextLabel: "编排 Analysis Workflow",
    nextRoute: "analysis-workflow"
  },
  "analysis-workflow": {
    goal: "把先理解、先对口径、再执行、再回答落实到流程。",
    primaryTask: "配置任务识别、澄清补全、语义映射、Runtime 取数、风险审查和反馈沉淀。",
    nextLabel: "沉淀 Case",
    nextRoute: "case-library"
  },
  "case-library": {
    goal: "把上线要求转成可重复执行的 Case。",
    primaryTask: "维护黄金 Case、澄清 Case、拒答 Case、红队 Case 和 Bad Case 回归样例。",
    nextLabel: "运行 Eval",
    nextRoute: "eval-runs"
  },
  "eval-runs": {
    goal: "用评测结果决定 Agent 和 Runtime 配置能否发布。",
    primaryTask: "选择 Agent 版本、Runtime 版本和 Case 集，查看通过率与失败分布。",
    nextLabel: "处理 Bad Case",
    nextRoute: "bad-case-workbench"
  },
  "bad-case-workbench": {
    goal: "把失败问答从发现、归因、修复、回归到发布验证串起来。",
    primaryTask: "关联 Trace、语义层、Prompt、Policy 和 Case，推动 Bad Case 进入回归 Eval。",
    nextLabel: "查看 Trace / Audit",
    nextRoute: "trace-audit"
  },
  "trace-audit": {
    goal: "追踪每次问答从意图识别到最终回答的安全链路。",
    primaryTask: "查看工具调用、SQL、权限裁决、DLP、Langfuse Trace 和用户反馈。",
    nextLabel: "查看审批中心",
    nextRoute: "approval-center"
  },
  "release-center": {
    goal: "把 Runtime 与 Data&QA Product 的版本发布、环境差异、检查和回滚集中管理。",
    primaryTask: "对比环境差异、运行发布前检查、提交审批、发布和回滚到稳定版本。",
    nextLabel: "回到首页总览",
    nextRoute: "dashboard"
  }
};

const dashboard: PageConfig = {
  route: "dashboard",
  title: "Data Agent Console",
  eyebrow: "运营驾驶舱",
  description: "统一查看 Runtime 安全链路、Data&QA 产品质量、评测门禁、发布状态和审计风险。",
  mode: "read",
  primaryAction: "编辑看板备注",
  modalTitle: "编辑看板备注",
  guardrail: "Dashboard 只读展示生产风险，不直接修改 Runtime 或 Data&QA 配置。",
  metrics: [],
  columns: [
    { key: "name", label: "对象" },
    { key: "scope", label: "范围" },
    { key: "status", label: "状态", tone: "status" },
    { key: "risk", label: "风险", tone: "risk" },
    { key: "owner", label: "负责人" }
  ],
  fields: [
    { key: "name", label: "备注标题", type: "text", required: true },
    { key: "scope", label: "关注范围", type: "select", options: ["Runtime", "Data&QA", "Eval", "Audit"] },
    { key: "status", label: "状态", type: "select", options: ["open", "tracking", "resolved"] },
    { key: "risk", label: "风险", type: "select", options: ["G1", "G2", "G3", "G4", "G5"] },
    { key: "owner", label: "负责人", type: "text", required: true }
  ],
  records: []
};

export const pageConfigs: PageConfig[] = [
  dashboard,
  {
    route: "runtime-overview",
    title: "Runtime Overview",
    eyebrow: "Runtime 总览页",
    description: "查看服务状态、工具调用量、SQL 拦截、DLP 命中、待审批任务和最近异常。",
    mode: "read",
    primaryAction: "新增异常备注",
    modalTitle: "编辑 Runtime 异常",
    guardrail: "异常处置、回滚、红队复测必须进入发布或审批流程，不能在总览页直接绕过。",
    metrics: [],
    columns: [
      { key: "name", label: "异常摘要" },
      { key: "component", label: "组件" },
      { key: "status", label: "状态", tone: "status" },
      { key: "risk", label: "风险", tone: "risk" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "异常摘要", type: "text", required: true },
      { key: "component", label: "组件", type: "select", options: ["Policy", "SQL Gateway", "DLP", "Audit", "Connector"] },
      { key: "status", label: "状态", type: "select", options: ["open", "investigating", "resolved"] },
      { key: "risk", label: "风险等级", type: "select", options: ["G1", "G2", "G3", "G4", "G5"] },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "connectors",
    title: "Connector / DataSource",
    eyebrow: "Runtime 配置中心",
    description: "新增连接器、测试连接、配置只读账号、绑定环境，并查看可用 Schema / Table。",
    mode: "config",
    primaryAction: "新增连接器",
    modalTitle: "连接器配置",
    guardrail: "敏感凭证只保存 secret_ref；生产真实 Connector 启用必须审批、发布和审计。",
    metrics: [],
    columns: [
      { key: "name", label: "连接器" },
      { key: "provider", label: "Provider" },
      { key: "environment", label: "环境" },
      { key: "accessMode", label: "访问模式" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "连接器名称", type: "text", required: true },
      { key: "provider", label: "Provider", type: "select", options: ["starrocks", "openmetadata", "langfuse", "custom"] },
      { key: "environment", label: "环境", type: "select", options: ["dev", "test", "staging", "prod"] },
      { key: "accessMode", label: "访问模式", type: "select", options: ["read_only", "metadata_only"] },
      { key: "secretRef", label: "secret_ref", type: "text", required: true },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "datatools",
    title: "DataTool Registry",
    eyebrow: "Runtime 配置中心",
    description: "注册工具、配置入参出参、风险等级、Plan Mode 和调用权限。",
    mode: "config",
    primaryAction: "注册工具",
    modalTitle: "DataTool 配置",
    guardrail: "Data&QA 只能绑定已发布 DataTool；高风险或非只读工具必须走 Plan Mode。",
    metrics: [],
    columns: [
      { key: "name", label: "工具" },
      { key: "intent", label: "工具意图" },
      { key: "risk", label: "风险", tone: "risk" },
      { key: "planMode", label: "Plan Mode" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "工具名称", type: "text", required: true },
      { key: "intent", label: "工具意图", type: "select", options: ["query_metric", "search_metadata", "explain_metric", "run_governance_task"] },
      { key: "risk", label: "风险等级", type: "select", options: ["G1", "G2", "G3", "G4", "G5"] },
      { key: "planMode", label: "需要 Plan Mode", type: "select", options: ["yes", "no"] },
      { key: "inputSchema", label: "入参摘要", type: "textarea" },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "policy-engine",
    title: "Policy Engine",
    eyebrow: "Runtime 配置中心",
    description: "管理 RBAC / ABAC、数据域权限、敏感等级权限、行列权限和审批策略。",
    mode: "config",
    primaryAction: "新增策略",
    modalTitle: "Policy 规则配置",
    guardrail: "策略无匹配时默认 DENY；放宽 ALLOW、降低敏感等级或绕过审批都必须提交审批。",
    metrics: [],
    columns: [
      { key: "name", label: "策略" },
      { key: "subject", label: "主体" },
      { key: "resource", label: "资源" },
      { key: "decision", label: "裁决", tone: "decision" },
      { key: "risk", label: "风险", tone: "risk" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "策略名称", type: "text", required: true },
      { key: "subject", label: "主体", type: "select", options: ["manager", "data_team", "operation_team", "agent_runtime"] },
      { key: "resource", label: "资源范围", type: "text", required: true },
      { key: "decision", label: "裁决", type: "select", options: ["ALLOW", "ASK", "DENY"] },
      { key: "risk", label: "风险", type: "select", options: ["G1", "G2", "G3", "G4", "G5"] },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "sql-gateway",
    title: "SQL Gateway",
    eyebrow: "Runtime 配置中心",
    description: "配置 SQL Dry Run、Explain、最大扫描量、超时、禁止 DDL/DML 和查询结果行数限制。",
    mode: "config",
    primaryAction: "新增 SQL 规则",
    modalTitle: "SQL Gateway 规则",
    guardrail: "DDL/DML、SELECT *、无 LIMIT、大扫描量和敏感字段查询默认 ASK 或 DENY。",
    metrics: [],
    columns: [
      { key: "name", label: "规则" },
      { key: "pattern", label: "匹配条件" },
      { key: "decision", label: "裁决", tone: "decision" },
      { key: "limitRows", label: "结果行数" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "规则名称", type: "text", required: true },
      { key: "pattern", label: "匹配条件", type: "select", options: ["select_star", "ddl_dml", "missing_limit", "sensitive_field", "large_scan"] },
      { key: "decision", label: "裁决", type: "select", options: ["ALLOW", "ASK", "DENY"] },
      { key: "limitRows", label: "结果行数限制", type: "number", required: true },
      { key: "timeoutSeconds", label: "超时秒数", type: "number", required: true },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "dlp-masking",
    title: "DLP / Masking",
    eyebrow: "Runtime 配置中心",
    description: "配置敏感标签、脱敏规则、展示层动态脱敏、导出限制和字段级命中日志预览。",
    mode: "config",
    primaryAction: "新增脱敏规则",
    modalTitle: "DLP / Masking 规则",
    guardrail: "PII、客户联系方式、明细导出和模型上下文写入默认不展示明文；放宽脱敏必须审批、发布和审计。",
    metrics: [],
    columns: [
      { key: "name", label: "规则" },
      { key: "fieldTag", label: "敏感标签" },
      { key: "maskingMethod", label: "脱敏方式" },
      { key: "exportDecision", label: "导出裁决", tone: "decision" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "规则名称", type: "text", required: true },
      { key: "fieldTag", label: "敏感标签", type: "select", options: ["customer_phone", "customer_email", "customer_name", "address", "order_detail"] },
      { key: "maskingMethod", label: "脱敏方式", type: "select", options: ["partial_mask", "hash", "redact", "aggregate_only"] },
      { key: "exportDecision", label: "导出裁决", type: "select", options: ["ALLOW", "ASK", "DENY"] },
      { key: "preview", label: "展示预览", type: "text", required: true },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "agent-apps",
    title: "Data&QA Agent Apps",
    eyebrow: "Data&QA 产品配置",
    description: "管理 RMA 问数助手、ERP 数据治理助手、知识库问答助手和自定义 Agent。",
    mode: "config",
    primaryAction: "新建 Agent",
    modalTitle: "Agent 应用配置",
    guardrail: "Agent 只能绑定 Runtime 发布环境和受控 DataTool，不能配置数据库 endpoint 或凭证。",
    metrics: [],
    columns: [
      { key: "name", label: "Agent" },
      { key: "domain", label: "业务域" },
      { key: "runtime", label: "Runtime 绑定" },
      { key: "evalStatus", label: "Eval" },
      { key: "status", label: "发布状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "Agent 名称", type: "text", required: true },
      { key: "domain", label: "业务域", type: "select", options: ["RMA 售后", "ERP 治理", "知识库", "自定义"] },
      { key: "runtime", label: "Runtime 版本", type: "select", options: ["prod-runtime-0.00.1", "staging-runtime-0.00.1"] },
      { key: "tasks", label: "任务范围", type: "textarea" },
      { key: "evalStatus", label: "Eval 状态", type: "select", options: ["not_run", "running", "passed", "failed", "blocked"] },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "semantic-layer",
    title: "Semantic Layer",
    eyebrow: "Data&QA 产品配置",
    description: "配置指标、维度、实体、同义词、时间口径、过滤条件和表字段映射。",
    mode: "config",
    primaryAction: "新增语义对象",
    modalTitle: "语义层配置",
    guardrail: "语义层只保存业务口径与受控资产引用，不能保存连接凭证或绕过 Runtime 的表访问方式。",
    metrics: [],
    columns: [
      { key: "name", label: "名称" },
      { key: "objectType", label: "类型" },
      { key: "sourceField", label: "字段映射" },
      { key: "timeGrain", label: "时间口径" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "名称", type: "text", required: true },
      { key: "objectType", label: "类型", type: "select", options: ["metric", "dimension", "entity", "synonym", "filter"] },
      { key: "definition", label: "业务定义", type: "textarea", required: true },
      { key: "sourceField", label: "字段映射", type: "text", required: true },
      { key: "timeGrain", label: "时间口径", type: "select", options: ["stat_date", "order_date", "rma_created_date", "month"] },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "analysis-workflow",
    title: "Analysis Workflow",
    eyebrow: "Data&QA 产品配置",
    description: "配置问题接入、任务识别、澄清补全、语义映射、取数规划、执行分析、结果合成、风险审查和反馈沉淀。",
    mode: "config",
    primaryAction: "新增工作流",
    modalTitle: "分析工作流配置",
    guardrail: "工作流必须先理解、先对口径、再执行、再回答；执行阶段只能调用 Runtime DataTool。",
    metrics: [],
    columns: [
      { key: "name", label: "工作流" },
      { key: "taskLevel", label: "任务等级" },
      { key: "clarification", label: "澄清策略" },
      { key: "runtimeTool", label: "Runtime 工具" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "工作流名称", type: "text", required: true },
      { key: "taskLevel", label: "任务等级", type: "select", options: ["L1", "L2", "L3", "L4"] },
      { key: "clarification", label: "澄清策略", type: "select", options: ["required_when_missing_time", "required_when_ambiguous", "none"] },
      { key: "runtimeTool", label: "Runtime 工具", type: "select", options: ["query_rma_metric_sql", "get_metric_definition", "search_metadata"] },
      { key: "steps", label: "步骤摘要", type: "textarea" },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "case-library",
    title: "Case Library",
    eyebrow: "Case / Eval 中心",
    description: "管理问题、任务类型、业务场景、期望澄清、工具调用、SQL、答案、口径、权限期望和拒答期望。",
    mode: "config",
    primaryAction: "新增 Case",
    modalTitle: "Case 配置",
    guardrail: "Case 不保存真实 PII、凭证或敏感原始 SQL；负向和红队 Case 必须覆盖拒答期望。",
    metrics: [],
    columns: [
      { key: "name", label: "Case" },
      { key: "caseType", label: "类型" },
      { key: "taskType", label: "任务类型" },
      { key: "decision", label: "权限期望", tone: "decision" },
      { key: "refuse", label: "拒答" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "Case 名称", type: "text", required: true },
      { key: "question", label: "用户问题", type: "textarea", required: true },
      { key: "caseType", label: "类型", type: "select", options: ["golden", "clarification", "negative", "red_team", "bad_case", "regression"] },
      { key: "taskType", label: "任务类型", type: "select", options: ["L1 查询取数", "L1 指标解释", "L2 异常诊断", "L3 归因分析", "L4 业务建议"] },
      { key: "decision", label: "权限期望", type: "select", options: ["ALLOW", "ASK", "DENY"] },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "eval-runs",
    title: "Eval Runs",
    eyebrow: "Case / Eval 中心",
    description: "选择 Agent 版本、Runtime 版本、Case 集运行评测，并查看通过率和失败分布。",
    mode: "run",
    primaryAction: "新建 Eval Run",
    modalTitle: "Eval Run 配置",
    guardrail: "Eval 不连接真实数据库；上线门禁以 Runtime Audit、Product Eval 和安全红队共同裁决。",
    metrics: [],
    columns: [
      { key: "name", label: "评测运行" },
      { key: "agentVersion", label: "Agent 版本" },
      { key: "runtimeVersion", label: "Runtime 版本" },
      { key: "passRate", label: "通过率" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "运行人" }
    ],
    fields: [
      { key: "name", label: "运行名称", type: "text", required: true },
      { key: "agentVersion", label: "Agent 版本", type: "select", options: ["rma-agent-0.00.1", "erp-agent-draft-0.00.1"] },
      { key: "runtimeVersion", label: "Runtime 版本", type: "select", options: ["runtime-0.00.1", "runtime-0.00.0"] },
      { key: "caseSuite", label: "Case 集", type: "select", options: ["rma-release-gate", "security-red-team", "smoke-suite"] },
      { key: "passRate", label: "通过率", type: "text" },
      { key: "owner", label: "运行人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "bad-case-workbench",
    title: "Bad Case Workbench",
    eyebrow: "Case / Eval 中心",
    description: "处理 Bad Case 的发现、归因、修复建议、关联配置对象、回归测试和发布验证。",
    mode: "config",
    primaryAction: "新增 Bad Case",
    modalTitle: "Bad Case 处理单",
    guardrail: "Bad Case 可以关联 SQL hash、Trace ID 和脱敏证据，但不能保存真实敏感明文或绕过 Runtime 重放。",
    metrics: [],
    columns: [
      { key: "name", label: "Bad Case" },
      { key: "rootCause", label: "失败归因" },
      { key: "linkedObject", label: "关联对象" },
      { key: "regression", label: "回归 Eval" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "Bad Case 名称", type: "text", required: true },
      { key: "question", label: "用户问题", type: "textarea", required: true },
      { key: "rootCause", label: "失败归因", type: "select", options: ["semantic_layer", "prompt_skill", "policy", "sql_gateway", "answer_template"] },
      { key: "linkedObject", label: "关联对象", type: "text", required: true },
      { key: "regression", label: "回归 Eval", type: "select", options: ["not_added", "case_added", "eval_running", "passed", "failed"] },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "approval-center",
    title: "Approval Center",
    eyebrow: "观测与审计中心",
    description: "统一处理 Plan Mode、高风险 SQL、策略变更、DLP 放宽、发布和回滚审批。",
    mode: "config",
    primaryAction: "新增审批单",
    modalTitle: "审批单",
    guardrail: "所有高风险配置和生产发布必须记录风险原因、影响对象、审批人、版本与回滚目标。",
    metrics: [],
    columns: [
      { key: "name", label: "审批事项" },
      { key: "riskReason", label: "风险原因" },
      { key: "impactObject", label: "影响对象" },
      { key: "rollbackVersion", label: "回滚版本" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "发起人" }
    ],
    fields: [
      { key: "name", label: "审批事项", type: "text", required: true },
      { key: "riskReason", label: "风险原因", type: "textarea", required: true },
      { key: "impactObject", label: "影响对象", type: "text", required: true },
      { key: "rollbackVersion", label: "回滚版本", type: "select", options: ["0.00.1", "0.00.0"] },
      { key: "approver", label: "审批人", type: "select", options: ["安全合规", "平台管理员", "数据治理负责人"] },
      { key: "owner", label: "发起人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "release-center",
    title: "Release Center",
    eyebrow: "发布与环境管理",
    description: "管理 Runtime Release、Product Release、环境差异、发布前检查和回滚入口。",
    mode: "config",
    primaryAction: "新建发布",
    modalTitle: "发布单",
    guardrail: "生产发布必须绑定审批单、Eval Run、Audit 引用和回滚版本；Data&QA Product 不能发布到未受 Runtime 管控的环境。",
    metrics: [],
    columns: [
      { key: "name", label: "发布对象" },
      { key: "releaseType", label: "发布类型" },
      { key: "environment", label: "环境" },
      { key: "precheck", label: "发布前检查" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "发布对象", type: "text", required: true },
      { key: "releaseType", label: "发布类型", type: "select", options: ["runtime_release", "product_release", "rollback"] },
      { key: "environment", label: "环境", type: "select", options: ["dev", "test", "staging", "prod"] },
      { key: "precheck", label: "发布前检查", type: "select", options: ["not_run", "passed", "failed", "blocked"] },
      { key: "rollbackVersion", label: "回滚版本", type: "select", options: ["0.00.1", "0.00.0"] },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  },
  {
    route: "trace-audit",
    title: "Trace / Audit Logs",
    eyebrow: "观测与审计中心",
    description: "查看用户问题、任务识别、澄清、语义映射、工具调用、SQL、权限、DLP、最终回答和反馈。",
    mode: "read",
    primaryAction: "新增审计备注",
    modalTitle: "Trace / Audit 备注",
    guardrail: "Trace 可显示 SQL 摘要、SQL hash 和审计引用，不展示未授权原始明细或敏感结果。",
    metrics: [],
    columns: [
      { key: "name", label: "Trace" },
      { key: "question", label: "用户问题摘要" },
      { key: "decision", label: "权限", tone: "decision" },
      { key: "dlp", label: "DLP" },
      { key: "status", label: "状态", tone: "status" },
      { key: "owner", label: "负责人" }
    ],
    fields: [
      { key: "name", label: "Trace 名称", type: "text", required: true },
      { key: "question", label: "问题摘要", type: "textarea", required: true },
      { key: "decision", label: "权限裁决", type: "select", options: ["ALLOW", "ASK", "DENY"] },
      { key: "dlp", label: "DLP 结果", type: "select", options: ["masked", "blocked", "none"] },
      { key: "langfuseId", label: "Langfuse Trace ID", type: "text" },
      { key: "owner", label: "负责人", type: "text", required: true }
    ],
    records: []
  }
];

export const pageConfigByRoute = Object.fromEntries(pageConfigs.map((page) => [page.route, page])) as Record<
  PageConfig["route"],
  PageConfig
>;
