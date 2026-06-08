import { useState } from "react";
import { apiGet, apiPost } from "../api/client";
import { displayLabel } from "../displayLabels";
import type { Translate } from "../types";

type WorkbenchTab = "simulator" | "jobs";

interface SQLReviewResponse {
  trace_id: string;
  audit_refs: string[];
  allowed: boolean;
  decision: "allow" | "ask" | "deny";
  risks: Array<{ risk_type: string; severity?: string; message?: string; reason?: string; target?: string | null }>;
  rewritten_sql?: string | null;
  reason: string;
  required_approval: boolean;
}

interface ToolDryRunResponse {
  trace_id: string;
  audit_refs: string[];
  tool_name: string;
  status: string;
  result: {
    status?: string;
    output?: Record<string, unknown>;
    error_message?: string | null;
    masked_fields?: string[];
  };
}

interface AuditResponse {
  events: Array<{ event_id: string; action: string; outcome: string; reason?: string | null }>;
}

interface TaskResponse {
  task_id: string;
  trace_id: string;
  audit_refs: string[];
  status: string;
  task_type: string;
  task_level: string;
}

interface TaskRunResponse {
  status: string;
  task_id: string;
  trace_id: string;
  audit_refs: string[];
  steps?: Array<{ node: string; status: string; observation?: string | null }>;
  evidence?: Array<Record<string, unknown>>;
  recommendations?: string[];
  business_result?: BusinessResult;
  executed_nodes?: string[];
  required_approvals?: Array<{ plan_id: string; risk_level: string; required_approvers: string[] }>;
  final_response?: string;
}

interface PlanDecisionResponse {
  plan_id: string;
  state: string;
  trace_id: string;
  audit_refs: string[];
}

interface BusinessMetric {
  label: string;
  value: string | number;
}

interface BusinessSection {
  type: string;
  title: string;
  columns?: string[];
  rows: Array<Record<string, unknown>>;
}

interface BusinessResult {
  title: string;
  task_type: string;
  task_level: string;
  status: string;
  summary: string;
  metrics: BusinessMetric[];
  sections: BusinessSection[];
  next_actions: string[];
  approval_required: boolean;
}

interface GovernanceTemplate {
  id: string;
  label: string;
  description: string;
  prompt: string;
  risk: string;
}

const simulatorSamples = {
  safe: {
    label: "安全查询",
    tool: "query_sql",
    riskLevel: "low",
    sql: "select metric_date, complaint_rate from ads_rma_metric_1d where metric_date = '2026-06-01' limit 20"
  },
  risky: {
    label: "高风险 SQL",
    tool: "query_sql",
    riskLevel: "high",
    sql: "select * from ods_erp_or_rma_order"
  },
  pii: {
    label: "PII 导出",
    tool: "query_sql",
    riskLevel: "critical",
    sql: "select customer_phone, customer_email from dwd_customer_detail_d limit 10000"
  },
  ddl: {
    label: "DDL / DML 红队",
    tool: "query_sql",
    riskLevel: "critical",
    sql: "delete from ads_rma_metric_1d where metric_date = '2026-06-01'"
  }
};

const governanceTemplates: GovernanceTemplate[] = [
  {
    id: "asset_inventory",
    label: "资产盘点",
    description: "识别 RMA 域核心表、Owner、敏感等级和治理缺口",
    prompt: "盘点 RMA 域核心数据资产",
    risk: "G2"
  },
  {
    id: "sensitive_data_discovery",
    label: "敏感字段识别",
    description: "发现 PII 字段、脱敏要求和模型上下文限制",
    prompt: "帮我识别 RMA 域敏感字段，并给出脱敏建议",
    risk: "G4"
  },
  {
    id: "data_quality",
    label: "质量规则建议",
    description: "生成完整性、及时性、枚举和范围校验规则",
    prompt: "为 RMA 指标表生成质量规则建议",
    risk: "G2"
  },
  {
    id: "metadata_completion",
    label: "元数据补全",
    description: "找出字段注释、Owner、数据字典缺口",
    prompt: "补全 RMA 明细表字段注释和数据字典",
    risk: "G2"
  },
  {
    id: "metric_governance",
    label: "指标口径治理",
    description: "检查指标定义、聚合粒度、时间口径和来源",
    prompt: "检查 RMA 客诉率指标口径",
    risk: "G3"
  },
  {
    id: "permission_inspection",
    label: "权限巡检",
    description: "检查高敏字段、财务字段和角色权限风险",
    prompt: "检查客户域权限策略",
    risk: "G4"
  },
  {
    id: "lineage_impact",
    label: "血缘影响分析",
    description: "分析上游变更对指标、看板、问数助手的影响",
    prompt: "分析 RMA 指标表下游血缘影响",
    risk: "G3"
  },
  {
    id: "data_domain_governance",
    label: "数据域治理",
    description: "检查数据域归属、治理责任和 Runtime 策略联动",
    prompt: "梳理 RMA 域治理缺口并给出整改建议",
    risk: "G4"
  },
  {
    id: "governance_report",
    label: "治理报告",
    description: "输出给管理者和数据团队的治理摘要",
    prompt: "生成 RMA 数据治理报告",
    risk: "G2"
  }
];

const sectionKeyMap: Record<string, string[]> = {
  asset_table: ["name", "layer", "domain", "owner", "sensitivity", "fields", "issues", "action"],
  sensitive_field_table: ["field", "table", "level", "risk", "rule"],
  quality_rule_table: ["rule", "target", "priority", "impact", "action"],
  metadata_table: ["object", "missing", "impact", "action"],
  permission_table: ["object", "risk", "decision", "action"],
  lineage_table: ["source", "target", "impact", "action"],
  domain_gap_table: ["object", "issue", "action"]
};

const rmaSqlAssetContext = {
  known_tables: [
    "ads_rma_metric_1d",
    "ods_erp_or_rma_order",
    "dwd_customer_detail_d",
    "dwd_after_sale_rma_detail_d",
    "ads_order_summary",
    "ods_order_detail"
  ],
  table_domains: {
    ads_rma_metric_1d: "after_sale",
    ods_erp_or_rma_order: "after_sale",
    dwd_customer_detail_d: "customer",
    dwd_after_sale_rma_detail_d: "after_sale",
    ads_order_summary: "trade",
    ods_order_detail: "trade"
  },
  column_sensitivity: {
    customer_phone: "L3",
    customer_email: "L3",
    shipping_address: "L3",
    customer_address: "L3"
  }
};

function decisionClass(value?: string) {
  return `tag decision-${String(value || "ask").toLowerCase()}`;
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function deriveRuntimeControls(input: { sql: string; riskLevel: string; tool: string; maxScanMb: number; rowLimit: number }) {
  const normalizedSql = input.sql.toLowerCase();
  const hasSelectStar = /select\s+\*/i.test(input.sql);
  const hasDdlOrDml = /\b(delete|update|insert|drop|alter|create|truncate|merge)\b/i.test(input.sql);
  const hasPii = /\b(phone|mobile|email|address|id_card|customer_phone|customer_email)\b/i.test(normalizedSql);
  const touchesRawLayer = /\b(ods_|dwd_customer|customer_detail)\b/i.test(normalizedSql);
  const isHighRisk = ["high", "critical"].includes(input.riskLevel);
  const isLargeQuery = input.maxScanMb > 512 || input.rowLimit > 5000;
  const mustDeny = hasSelectStar || hasDdlOrDml || (hasPii && input.tool === "query_sql");
  const requiresApproval = !mustDeny && (isHighRisk || hasPii || touchesRawLayer || isLargeQuery);
  const allowInModelContext = input.tool !== "query_sql" && !requiresApproval && !hasPii && !touchesRawLayer;
  const decision = mustDeny ? "deny" : requiresApproval ? "ask" : "allow";

  const reasons = [
    isHighRisk ? "风险等级达到高或严重" : null,
    hasSelectStar ? "SQL 包含 SELECT *" : null,
    hasDdlOrDml ? "SQL 包含 DDL / DML" : null,
    hasPii ? "疑似访问 PII 字段" : null,
    touchesRawLayer ? "访问 ODS 或客户明细层" : null,
    isLargeQuery ? "扫描量或行数超过安全阈值" : null,
    input.tool === "query_sql" && !requiresApproval ? "SQL 工具结果默认只允许脱敏摘要进入回答链路" : null
  ].filter(Boolean) as string[];

  return {
    decision,
    requiresApproval,
    requestRequiresApproval: requiresApproval || isHighRisk,
    allowInModelContext,
    reasons: reasons.length ? reasons : ["低风险受控请求，仍由 Runtime Policy / DLP 最终裁决"]
  };
}

export function RuntimeWorkbenchPage({ t }: { t: Translate }) {
  const [tab, setTab] = useState<WorkbenchTab>("simulator");
  const [role, setRole] = useState("data_team");
  const [agent, setAgent] = useState("RMA 问数助手");
  const [tool, setTool] = useState("query_sql");
  const [riskLevel, setRiskLevel] = useState("low");
  const [maxScanMb, setMaxScanMb] = useState(256);
  const [timeoutSeconds, setTimeoutSeconds] = useState(30);
  const [rowLimit, setRowLimit] = useState(500);
  const [sql, setSql] = useState(simulatorSamples.safe.sql);
  const [review, setReview] = useState<SQLReviewResponse | null>(null);
  const [toolResult, setToolResult] = useState<ToolDryRunResponse | null>(null);
  const [audit, setAudit] = useState<AuditResponse | null>(null);
  const [simulatorError, setSimulatorError] = useState<string | null>(null);
  const [simulatorActionMessage, setSimulatorActionMessage] = useState<string | null>(null);
  const [simulatorLoading, setSimulatorLoading] = useState(false);

  const [taskPrompt, setTaskPrompt] = useState("帮我识别 RMA 域敏感字段，并给出脱敏建议");
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [taskRun, setTaskRun] = useState<TaskRunResponse | null>(null);
  const [planDecision, setPlanDecision] = useState<PlanDecisionResponse | null>(null);
  const [jobAudit, setJobAudit] = useState<AuditResponse | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [jobLoading, setJobLoading] = useState(false);

  const applySample = (sample: keyof typeof simulatorSamples) => {
    const next = simulatorSamples[sample];
    setTool(next.tool);
    setRiskLevel(next.riskLevel);
    setSql(next.sql);
    setSimulatorActionMessage(null);
  };

  const applyGovernanceTemplate = (template: GovernanceTemplate) => {
    setTaskPrompt(template.prompt);
    setTask(null);
    setTaskRun(null);
    setPlanDecision(null);
    setJobAudit(null);
    setJobError(null);
  };

  const runtimeControls = deriveRuntimeControls({ sql, riskLevel, tool, maxScanMb, rowLimit });

  const runSimulator = async () => {
    setSimulatorLoading(true);
    setSimulatorError(null);
    setSimulatorActionMessage(null);
    try {
      const reviewResult = await apiPost<SQLReviewResponse>("/sql/review", {
        sql,
        asset_context: rmaSqlAssetContext
      });
      setReview(reviewResult);
      const dryRun = await apiPost<ToolDryRunResponse>(`/tools/${tool}/dry-run`, {
        parameters: { sql, asset_context: rmaSqlAssetContext, max_scan_mb: maxScanMb, timeout_seconds: timeoutSeconds, row_limit: rowLimit },
        risk_level: riskLevel,
        requires_approval: runtimeControls.requestRequiresApproval,
        allow_in_model_context: runtimeControls.allowInModelContext
      });
      setToolResult(dryRun);
      setAudit(await apiGet<AuditResponse>("/audit"));
    } catch (error) {
      setSimulatorError(error instanceof Error ? error.message : "Runtime simulator failed.");
    } finally {
      setSimulatorLoading(false);
    }
  };

  const loadAuditFromError = async () => {
    setSimulatorActionMessage(null);
    try {
      const latestAudit = await apiGet<AuditResponse>("/audit");
      setAudit(latestAudit);
      setSimulatorActionMessage(`已读取 ${latestAudit.events.length} 条审计事件，详见右侧或下方 Audit Events。`);
    } catch (error) {
      setSimulatorActionMessage(`审计读取失败：${error instanceof Error ? error.message : "Runtime API 不可用"}`);
    }
  };

  const createRuntimeBadCase = () => {
    setSimulatorActionMessage("已生成本地 Bad Case 草稿：Runtime 安全模拟失败，请关联当前 SQL、角色、工具和错误信息后进入 Bad Case 工作台回归。");
  };

  const runGovernanceJob = async () => {
    setJobLoading(true);
    setJobError(null);
    setPlanDecision(null);
    try {
      const created = await apiPost<TaskResponse>("/tasks", { user_prompt: taskPrompt });
      setTask(created);
      const run = await apiPost<TaskRunResponse>(`/tasks/${created.task_id}/run`, {});
      setTaskRun(run);
      setJobAudit(await apiGet<AuditResponse>(`/tasks/${created.task_id}/audit`));
    } catch (error) {
      setJobError(error instanceof Error ? error.message : "Governance job failed.");
    } finally {
      setJobLoading(false);
    }
  };

  const decidePlan = async (action: "approve" | "reject") => {
    const planId = taskRun?.required_approvals?.[0]?.plan_id;
    if (!planId) return;
    setJobLoading(true);
    setJobError(null);
    try {
      const result = await apiPost<PlanDecisionResponse>(`/plans/${planId}/${action}`, {
        approver: "mock_security_reviewer",
        reason: "Rejected from Runtime Workbench."
      });
      setPlanDecision(result);
    } catch (error) {
      setJobError(error instanceof Error ? error.message : `Plan ${action} failed.`);
    } finally {
      setJobLoading(false);
    }
  };

  const pendingApproval = taskRun?.required_approvals?.[0];
  const selectedTemplate = governanceTemplates.find((template) => template.prompt === taskPrompt);
  const approvalAfterValue = planDecision?.state ?? (pendingApproval ? "waiting_approval" : taskRun ? "not_required" : t("待运行"));
  const planModeValue = planDecision?.state ?? (pendingApproval ? "waiting_approval" : taskRun ? "not_required" : t("未触发"));

  return (
    <section className="page workbench-page runtime-console-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Runtime 使用工作台</p>
          <h2>{t("Runtime 使用工作台")}</h2>
          <p className="description">
            {t("直接使用 Data Governance Agent Runtime，验证 SQL、工具调用、Plan Mode、DLP / Masking 和 Audit 是否形成闭环。")}
          </p>
        </div>
        <div className="segmented-control" role="tablist" aria-label={t("Runtime 使用工作台页签")}>
          <button type="button" className={tab === "simulator" ? "active" : ""} onClick={() => setTab("simulator")}>
            {t("安全链路模拟器")}
          </button>
          <button type="button" className={tab === "jobs" ? "active" : ""} onClick={() => setTab("jobs")}>
            {t("治理作业台")}
          </button>
        </div>
      </div>

      {tab === "simulator" ? (
        <div className="workbench-layout">
          <section className="panel workbench-input">
            <div className="panel-toolbar">
              <div>
                <h3>{t("安全链路模拟器")}</h3>
                <p>{t("输入一次受控工具请求，观察 Runtime 如何裁决和审计")}</p>
              </div>
            </div>
            <div className="workbench-form">
              <div className="quick-actions">
                {Object.entries(simulatorSamples).map(([key, sample]) => (
                  <button key={key} type="button" className="ghost-button" onClick={() => applySample(key as keyof typeof simulatorSamples)}>
                    {t(sample.label)}
                  </button>
                ))}
              </div>
              <label className="form-field">
                <span>{t("用户角色")}</span>
                <select value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="manager">{displayLabel("manager", t)}</option>
                  <option value="data_team">{displayLabel("data_team", t)}</option>
                  <option value="operations">{displayLabel("operations", t)}</option>
                </select>
              </label>
              <label className="form-field">
                <span>Agent</span>
                <input value={agent} onChange={(event) => setAgent(event.target.value)} />
              </label>
              <label className="form-field">
                <span>{t("工具")}</span>
                <select value={tool} onChange={(event) => setTool(event.target.value)}>
                  <option value="query_sql">{displayLabel("query_sql", t)}</option>
                  <option value="search_metadata">{displayLabel("search_metadata", t)}</option>
                  <option value="get_metric_definition">{displayLabel("get_metric_definition", t)}</option>
                </select>
              </label>
              <label className="form-field">
                <span>{t("风险等级")}</span>
                <select value={riskLevel} onChange={(event) => setRiskLevel(event.target.value)}>
                  <option value="low">{displayLabel("low", t)}</option>
                  <option value="medium">{displayLabel("medium", t)}</option>
                  <option value="high">{displayLabel("high", t)}</option>
                  <option value="critical">{displayLabel("critical", t)}</option>
                </select>
              </label>
              <label className="form-field">
                <span>{t("最大扫描量 MB")}</span>
                <input type="number" value={maxScanMb} onChange={(event) => setMaxScanMb(Number(event.target.value))} />
              </label>
              <label className="form-field">
                <span>{t("超时秒数")}</span>
                <input type="number" value={timeoutSeconds} onChange={(event) => setTimeoutSeconds(Number(event.target.value))} />
              </label>
              <label className="form-field">
                <span>{t("结果行数限制")}</span>
                <input type="number" value={rowLimit} onChange={(event) => setRowLimit(Number(event.target.value))} />
              </label>
              <div className="auto-decision-card">
                <span>{t("审批 / 拦截机制")}</span>
                <strong>
                  {runtimeControls.decision === "deny"
                    ? t("自动拒绝执行")
                    : runtimeControls.decision === "ask"
                      ? t("自动进入审批")
                      : t("暂不需要审批")}
                </strong>
              </div>
              <div className="auto-decision-card">
                <span>{t("模型上下文准入")}</span>
                <strong>{runtimeControls.allowInModelContext ? t("允许脱敏摘要进入上下文") : t("禁止明文进入上下文")}</strong>
              </div>
              <div className="auto-decision-card span-all">
                <span>{t("自动裁决依据")}</span>
                <strong>{runtimeControls.reasons.map((reason) => t(reason)).join("；")}</strong>
              </div>
              <label className="form-field span-all">
                <span>{t("SQL / 工具输入")}</span>
                <textarea value={sql} onChange={(event) => setSql(event.target.value)} />
              </label>
              <button type="button" className="primary-button span-all" onClick={runSimulator} disabled={simulatorLoading}>
                {simulatorLoading ? t("运行中...") : t("运行安全模拟")}
              </button>
              {simulatorError ? (
                <div className="error-card span-all">
                  <strong>{t("Runtime API 不可用")}</strong>
                  <span>{simulatorError}</span>
                  <div className="quick-actions">
                    <button type="button" className="secondary-button" onClick={runSimulator}>
                      {t("重试")}
                    </button>
                    <button type="button" className="ghost-button" onClick={loadAuditFromError}>
                      {t("查看审计")}
                    </button>
                    <button type="button" className="ghost-button" onClick={createRuntimeBadCase}>
                      {t("转 Bad Case")}
                    </button>
                  </div>
                </div>
              ) : null}
              {simulatorActionMessage ? <p className="action-message span-all">{t(simulatorActionMessage)}</p> : null}
            </div>
          </section>

          <aside className="workbench-results pipeline-column">
            <PipelineCard title={t("策略引擎")} value={toolResult?.result.output?.policy_decision ?? toolResult?.status ?? t("待运行")} active={Boolean(toolResult)} t={t} />
            <PipelineCard title={t("SQL 网关")} value={review?.decision ?? t("待运行")} detail={review?.reason} active={Boolean(review)} t={t} />
            <PipelineCard title={t("DLP / 脱敏")} value={toolResult?.result.masked_fields?.length ? "masked" : review ? "none" : t("待运行")} active={Boolean(review)} t={t} />
            <PipelineCard title={t("计划审批")} value={review?.decision === "deny" ? "not_applicable" : review?.required_approval || runtimeControls.requiresApproval ? "approval_required" : review ? "not_required" : t("待运行")} active={Boolean(review)} t={t} />
            <PipelineCard title={t("审计事件")} value={audit?.events.length ? `${audit.events.length} ${t("条事件")}` : t("待读取")} active={Boolean(audit)} t={t} />
          </aside>

          <section className="panel span-wide">
            <div className="panel-toolbar">
              <div>
                <h3>{t("运行结果")}</h3>
                <p>{t("SQL 风险、工具结果和审计引用")}</p>
              </div>
              <div className="quick-actions">
                {review ? <span className={decisionClass(review.decision)}>{displayLabel(review.decision, t)}</span> : null}
                <button type="button" className="ghost-button" onClick={runSimulator} disabled={simulatorLoading}>
                  {t("重新运行")}
                </button>
              </div>
            </div>
            <div className="risk-explain">
              <strong>{t("SQL 风险解释")}</strong>
              <span>
                {review?.risks?.length
                  ? review.risks.map((risk) => `${displayLabel(risk.risk_type, t)}${risk.target ? `: ${risk.target}` : ""}`).join("；")
                  : t("运行后展示 SELECT *、DDL/DML、PII、扫描量、超时和行数限制命中原因。")}
              </span>
            </div>
            <div className="result-grid">
              <JsonDetails title={t("SQL 网关审查")} value={review ?? t("尚未运行 SQL 网关审查")} />
              <JsonDetails title={t("DataTool 试运行")} value={toolResult?.result ?? t("尚未运行 DataTool 试运行")} />
              <JsonDetails title={t("审计事件")} value={audit?.events.slice(-5) ?? t("尚未读取审计事件")} />
            </div>
          </section>
        </div>
      ) : (
        <div className="workbench-layout">
          <section className="panel workbench-input">
            <div className="panel-toolbar">
              <div>
                <h3>{t("治理作业台")}</h3>
                <p>{t("运行 Runtime 治理任务，并处理 Plan Mode 审批")}</p>
              </div>
            </div>
            <div className="workbench-form one-column">
              <div className="governance-template-grid">
                {governanceTemplates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    className={selectedTemplate?.id === template.id ? "governance-template active" : "governance-template"}
                    onClick={() => applyGovernanceTemplate(template)}
                  >
                    <span>{t(template.label)}</span>
                    <strong>{t(template.description)}</strong>
                    <em>{template.risk}</em>
                  </button>
                ))}
              </div>
              <label className="form-field">
                <span>{t("治理任务 Prompt")}</span>
                <textarea value={taskPrompt} onChange={(event) => setTaskPrompt(event.target.value)} />
              </label>
              <button type="button" className="primary-button" onClick={runGovernanceJob} disabled={jobLoading}>
                {jobLoading ? t("运行中...") : t("运行治理作业")}
              </button>
              {jobError ? <p className="error-text">{jobError}</p> : null}
            </div>
          </section>

          <aside className="workbench-results">
            <ResultCard title={t("治理任务")} value={task?.status ?? t("待创建")} detail={task ? `${displayLabel(task.task_type, t)} / ${task.task_level}` : undefined} t={t} />
            <ResultCard title={t("Runtime 运行")} value={taskRun?.status ?? t("待运行")} detail={taskRun?.final_response} t={t} />
            <ResultCard title={t("计划审批")} value={planModeValue} t={t} />
            <ResultCard title={t("审计事件")} value={jobAudit?.events.length ? `${jobAudit.events.length} ${t("条事件")}` : t("待读取")} t={t} />
          </aside>

          {pendingApproval ? (
            <section className="panel span-wide approval-card">
              <div>
                <p className="eyebrow">{t("Plan Mode / 审批")}</p>
                <h3>{t("高风险治理计划需要审批")}</h3>
                <p>
                  {t("审批计划 ID")}：{pendingApproval.plan_id} · {t("风险等级")}：{displayLabel(pendingApproval.risk_level, t)}
                </p>
              </div>
              <div className="page-actions">
                <button type="button" className="primary-button" onClick={() => decidePlan("approve")} disabled={jobLoading}>
                  {t("审批通过")}
                </button>
                <button type="button" className="secondary-button" onClick={() => decidePlan("reject")} disabled={jobLoading}>
                  {t("驳回")}
                </button>
              </div>
            </section>
          ) : null}

          <section className="panel span-wide">
            <div className="panel-toolbar">
              <div>
                <h3>{t("治理作业结果")}</h3>
                <p>{t("业务结果、执行节点、审批结果和审计引用")}</p>
              </div>
            </div>
            <BusinessResultPanel result={taskRun?.business_result} task={task} taskRun={taskRun} t={t} />
            <div className="governance-outcome-grid">
              <GovernanceTimeline steps={taskRun?.steps} t={t} />
              <ApprovalAuditPanel
                approvalBefore={pendingApproval ? "plan_required" : taskRun?.status ?? t("待运行")}
                approvalAfter={approvalAfterValue}
                planId={pendingApproval?.plan_id}
                auditCount={jobAudit?.events.length ?? 0}
                planDecision={planDecision}
                t={t}
              />
            </div>
            <details className="json-details technical-details">
              <summary>{t("技术详情 / 原始 JSON")}</summary>
              <pre>{formatJson({ task, taskRun, planDecision, recentAudit: jobAudit?.events.slice(-5) })}</pre>
            </details>
          </section>
        </div>
      )}
    </section>
  );
}

function BusinessResultPanel({ result, task, taskRun, t }: { result?: BusinessResult; task: TaskResponse | null; taskRun: TaskRunResponse | null; t: Translate }) {
  if (!taskRun) {
    return (
      <div className="business-empty">
        <strong>{t("等待运行治理作业")}</strong>
        <span>{t("选择一个治理任务模板，运行后这里会展示业务摘要、发现结果和下一步建议。")}</span>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="business-empty">
        <strong>{t("已完成技术执行，暂无业务化结果")}</strong>
        <span>{task ? `${displayLabel(task.task_type, t)} / ${task.task_level}` : t("请查看技术详情。")}</span>
      </div>
    );
  }

  return (
    <div className="business-result">
      <div className="business-summary">
        <div>
          <p className="eyebrow">{displayLabel(result.task_type, t)} / {displayLabel(result.task_level, t)}</p>
          <h3>{result.summary}</h3>
        </div>
        <span className={result.approval_required ? "tag decision-ask" : "tag decision-allow"}>
          {result.approval_required ? t("需要审批") : t("无需审批")}
        </span>
      </div>
      <div className="business-metrics">
        {result.metrics.map((metric) => (
          <article key={`${metric.label}-${metric.value}`}>
            <span>{t(metric.label)}</span>
            <strong>{displayLabel(metric.value, t)}</strong>
          </article>
        ))}
      </div>
      {result.sections.map((section) => (
        <BusinessSectionView key={`${section.type}-${section.title}`} section={section} t={t} />
      ))}
      <div className="next-actions-panel">
        <h4>{t("下一步建议")}</h4>
        <ul>
          {result.next_actions.map((action) => (
            <li key={action}>{t(action)}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function BusinessSectionView({ section, t }: { section: BusinessSection; t: Translate }) {
  if (section.type === "metric_card" || section.type === "report_summary") {
    return (
      <section className="business-section">
        <h4>{t(section.title)}</h4>
        <div className="business-kv-list">
          {section.rows.map((row) => (
            <div key={`${String(row.label)}-${String(row.value)}`}>
              <span>{t(String(row.label ?? ""))}</span>
              <strong>{displayLabel(row.value, t)}</strong>
            </div>
          ))}
        </div>
      </section>
    );
  }

  const keys = sectionKeyMap[section.type] ?? Object.keys(section.rows[0] ?? {});
  const headers = section.columns?.length === keys.length ? section.columns : keys;

  return (
    <section className="business-section">
      <h4>{t(section.title)}</h4>
      <div className="business-table-wrap">
        <table className="business-table">
          <thead>
            <tr>
              {headers.map((column) => (
                <th key={column}>{t(column)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {section.rows.map((row, rowIndex) => (
              <tr key={`${section.type}-${rowIndex}`}>
                {keys.map((key) => (
                  <td key={key}>{displayLabel(row[key], t)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function GovernanceTimeline({ steps, t }: { steps?: TaskRunResponse["steps"]; t: Translate }) {
  const visibleSteps = steps?.length
    ? steps
    : [
        { node: "request_intake", status: "not_run", observation: "等待接入任务" },
        { node: "task_classification", status: "not_run", observation: "等待任务分类" },
        { node: "asset_mapping", status: "not_run", observation: "等待资产映射" },
        { node: "risk_review", status: "not_run", observation: "等待风险审查" },
        { node: "result_synthesis", status: "not_run", observation: "等待结果生成" }
      ];

  return (
    <div className="governance-timeline-panel">
      <h4>{t("执行过程")}</h4>
      <div className="timeline-trace governance-timeline">
        {visibleSteps.map((step, index) => (
          <div key={`${step.node}-${index}`} className="timeline-node">
            <span>{index + 1}</span>
            <div>
              <strong>{displayLabel(step.node, t)}</strong>
              <em>{displayLabel(step.status, t)}</em>
              {step.observation ? <small>{t(step.observation)}</small> : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ApprovalAuditPanel({
  approvalBefore,
  approvalAfter,
  planId,
  auditCount,
  planDecision,
  t
}: {
  approvalBefore: unknown;
  approvalAfter: unknown;
  planId?: string;
  auditCount: number;
  planDecision: PlanDecisionResponse | null;
  t: Translate;
}) {
  return (
    <div className="approval-audit-panel">
      <h4>{t("审批与审计")}</h4>
      <div className="approval-compare compact">
        <ResultCard title={t("审批前")} value={approvalBefore} detail={planId} t={t} />
        <ResultCard title={t("审批后")} value={approvalAfter} detail={planDecision?.audit_refs?.join(", ")} t={t} />
      </div>
      <div className="audit-summary-row">
        <span>{t("审计事件")}</span>
        <strong>{auditCount ? `${auditCount} ${t("条事件")}` : t("待读取")}</strong>
      </div>
    </div>
  );
}

function JsonDetails({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="json-details">
      <summary>{title}</summary>
      <pre>{typeof value === "string" ? value : formatJson(value)}</pre>
    </details>
  );
}

function PipelineCard({ title, value, detail, active, t }: { title: string; value: unknown; detail?: string; active: boolean; t: Translate }) {
  return (
    <article className={active ? "result-card pipeline-card active" : "result-card pipeline-card"}>
      <p>{title}</p>
      <strong>{displayLabel(value, t)}</strong>
      {detail ? <span>{detail}</span> : null}
    </article>
  );
}

function ResultCard({ title, value, detail, t }: { title: string; value: unknown; detail?: string; t: Translate }) {
  return (
    <article className="result-card">
      <p>{title}</p>
      <strong>{displayLabel(value, t)}</strong>
      {detail ? <span>{detail}</span> : null}
    </article>
  );
}
