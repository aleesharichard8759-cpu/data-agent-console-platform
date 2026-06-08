import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../api/client";
import { displayJoinedLabels, displayLabel } from "../displayLabels";
import { sampleQuestionForLanguage } from "../i18n";
import type { Language, Translate } from "../types";

interface DataQARunResult {
  request: {
    user_query: string;
    audience: string;
  };
  structured_task: {
    task_id: string;
    task_type: string;
    task_level: string;
    metric?: string | null;
    dimensions: string[];
    time_range_label?: string | null;
    clarification_status: string;
    clarification_questions: string[];
  };
  semantic_intent: {
    standard_metrics: string[];
    standard_dimensions: string[];
    entities: string[];
    data_sources: string[];
    permission_decision: string;
    notes: string[];
  };
  execution_plan: {
    tool_sequence: string[];
    sql?: string | null;
    risk_checkpoints: string[];
  };
  answer: {
    status: string;
    summary: string;
    evidence: Array<Record<string, unknown>>;
    metric_definition?: string | null;
    sources: string[];
    limitations: string[];
    suggestions: string[];
    follow_up_questions: string[];
    audit_refs: string[];
  };
  trace: {
    trace_id: string;
    nodes: string[];
    tool_calls: string[];
    scores: Record<string, number>;
    failure_node?: string | null;
  };
}

interface StoredTaskResponse {
  result: DataQARunResult;
}

interface FeedbackResponse {
  feedback: {
    feedback_id: string;
    rating: string;
    error_type?: string | null;
    enter_bad_case: boolean;
  };
}

interface BadCasesResponse {
  count: number;
  bad_cases: Array<{ feedback_id: string; error_type?: string | null; comment?: string | null }>;
}

const sampleQuestions = [
  "本月 RMA 客诉率是多少？",
  "上周质量问题客诉为什么升高？",
  "导出所有退货客户手机号"
];

function listText(values: string[] | undefined, t: Translate) {
  return displayJoinedLabels(values, t);
}

function statusClass(value?: string) {
  const normalized = String(value || "open").toLowerCase();
  if (normalized === "complete" || normalized === "allow") return "tag decision-allow";
  if (normalized === "denied" || normalized === "deny") return "tag decision-deny";
  return "tag decision-ask";
}

export function DataQAWorkspacePage({ language, t }: { language: Language; t: Translate }) {
  const [agent, setAgent] = useState("RMA 问数助手");
  const [audience, setAudience] = useState("manager");
  const [environment, setEnvironment] = useState("prod");
  const [question, setQuestion] = useState(sampleQuestions[0]);
  const [result, setResult] = useState<DataQARunResult | null>(null);
  const [storedResult, setStoredResult] = useState<DataQARunResult | null>(null);
  const [feedbackRating, setFeedbackRating] = useState<"positive" | "negative">("positive");
  const [errorType, setErrorType] = useState("metric_mismatch");
  const [comment, setComment] = useState("");
  const [feedback, setFeedback] = useState<FeedbackResponse | null>(null);
  const [badCases, setBadCases] = useState<BadCasesResponse | null>(null);
  const [history, setHistory] = useState<Array<{ taskId: string; question: string; status: string }>>([]);
  const [caseCreated, setCaseCreated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const localizedQuestions = useMemo(() => sampleQuestions.map((sample) => t(sample)), [t]);

  useEffect(() => {
    setQuestion((current) => sampleQuestionForLanguage(current, language));
  }, [language]);

  const runQuestion = async () => {
    setLoading(true);
    setError(null);
    setFeedback(null);
    try {
      const run = await apiPost<DataQARunResult>("/data-qa/run", {
        user_query: question,
        audience,
        source: "agent_workspace",
        conversation_context: [`agent=${agent}`, `environment=${environment}`]
      });
      setResult(run);
      setHistory((current) => [{ taskId: run.structured_task.task_id, question, status: run.answer.status }, ...current].slice(0, 6));
      setCaseCreated(false);
      const stored = await apiGet<StoredTaskResponse>(`/data-qa/tasks/${run.structured_task.task_id}`);
      setStoredResult(stored.result);
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Data&QA run failed.");
    } finally {
      setLoading(false);
    }
  };

  const submitFeedback = async () => {
    if (!result) return;
    setFeedbackLoading(true);
    setError(null);
    try {
      const response = await apiPost<FeedbackResponse>("/data-qa/feedback", {
        task_id: result.structured_task.task_id,
        trace_id: result.trace.trace_id,
        rating: feedbackRating,
        error_type: feedbackRating === "negative" ? errorType : null,
        comment
      });
      setFeedback(response);
      if (feedbackRating === "negative") {
        setBadCases(await apiGet<BadCasesResponse>("/data-qa/bad-cases"));
      }
    } catch (apiError) {
      setError(apiError instanceof Error ? apiError.message : "Feedback submit failed.");
    } finally {
      setFeedbackLoading(false);
    }
  };

  const activeResult = storedResult ?? result;

  const copyText = async (value: string) => {
    try {
      await navigator.clipboard?.writeText(value);
    } catch {
      // Clipboard access is optional in the mock console.
    }
  };

  const createCaseFromResult = () => {
    if (!activeResult) return;
    setCaseCreated(true);
    setBadCases((current) => ({
      count: (current?.count ?? 0) + 1,
      bad_cases: [
        {
          feedback_id: `case-${activeResult.structured_task.task_id}`,
          error_type: "manual_case",
          comment: activeResult.request.user_query
        },
        ...(current?.bad_cases ?? [])
      ]
    }));
  };

  return (
    <section className="page workbench-page dataqa-console-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Agent 问数工作台</p>
          <h2>Agent Workspace</h2>
          <p className="description">
            {t("面向业务用户使用 RMA 问数助手，完整展示问题理解、口径对齐、Runtime 执行计划、答案、Trace 和反馈闭环。")}
          </p>
        </div>
      </div>

      <div className="workspace-layout">
        <section className="panel question-panel">
          <div className="panel-toolbar">
              <div>
              <h3>{t("RMA 问数输入")}</h3>
              <p>{t("Data&QA Product 只做理解和解释，执行必须走 Runtime DataTool")}</p>
            </div>
          </div>
          <div className="workbench-form">
            <label className="form-field">
              <span>Agent</span>
              <select value={agent} onChange={(event) => setAgent(event.target.value)}>
                <option value="RMA 问数助手">{t("RMA 问数助手")}</option>
                <option value="ERP 数据治理助手">{t("ERP 数据治理助手")}</option>
                <option value="知识库问答助手">{t("知识库问答助手")}</option>
              </select>
            </label>
            <label className="form-field">
              <span>{t("受众")}</span>
              <select value={audience} onChange={(event) => setAudience(event.target.value)}>
                <option value="manager">{displayLabel("manager", t)}</option>
                <option value="data_team">{displayLabel("data_team", t)}</option>
                <option value="operations">{displayLabel("operations", t)}</option>
              </select>
            </label>
            <label className="form-field">
              <span>{t("环境")}</span>
              <select value={environment} onChange={(event) => setEnvironment(event.target.value)}>
                <option value="prod">{displayLabel("prod", t)}</option>
                <option value="staging">{displayLabel("staging", t)}</option>
              </select>
            </label>
            <div className="quick-actions span-all">
              {sampleQuestions.map((sample, index) => (
                <button key={sample} type="button" className="ghost-button" onClick={() => setQuestion(localizedQuestions[index])}>
                  {localizedQuestions[index]}
                </button>
              ))}
            </div>
            <label className="form-field span-all">
              <span>{t("业务问题")}</span>
              <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
            </label>
            <button type="button" className="primary-button span-all" onClick={runQuestion} disabled={loading}>
              {loading ? t("分析中...") : t("运行问数分析")}
            </button>
            {error ? <p className="error-text span-all">{error}</p> : null}
          </div>
        </section>

        <aside className="trace-sidebar">
          <section className="panel">
            <div className="panel-toolbar">
              <div>
                <h3>Trace</h3>
                <p>{t("Langfuse / Runtime 审计占位")}</p>
              </div>
            </div>
            <div className="trace-list">
              <TraceItem label={t("Trace ID")} value={activeResult?.trace.trace_id ?? t("待运行")} />
              <TimelineTrace values={activeResult?.trace.nodes ?? []} t={t} />
              <TraceItem label={t("工具调用")} value={listText(activeResult?.trace.tool_calls, t)} />
              <TraceItem label={t("评分")} value={activeResult ? JSON.stringify(activeResult.trace.scores) : t("待运行")} />
              <TraceItem label={t("审计引用")} value={listText(activeResult?.answer.audit_refs, t)} />
            </div>
          </section>
          <section className="panel">
            <div className="panel-toolbar">
              <div>
                <h3>{t("历史会话")}</h3>
                <p>{t("最近 6 次问数运行")}</p>
              </div>
            </div>
            <div className="trace-list">
              {history.length ? (
                history.map((item) => <TraceItem key={item.taskId} label={displayLabel(item.status, t)} value={item.question} />)
              ) : (
                <div className="empty-state compact">
                  <strong>{t("暂无历史会话")}</strong>
                  <span>{t("运行一次 RMA 问数后会出现在这里。")}</span>
                </div>
              )}
            </div>
          </section>
        </aside>

        <section className="process-grid">
          <ProcessCard
            title={t("问题理解")}
            status={activeResult?.structured_task.clarification_status}
            rows={[
              ["任务类型", activeResult?.structured_task.task_type],
              ["等级", activeResult?.structured_task.task_level],
              ["指标", activeResult?.structured_task.metric],
              ["维度", listText(activeResult?.structured_task.dimensions, t)],
              ["时间范围", activeResult?.structured_task.time_range_label]
            ]}
            t={t}
          />
          <ProcessCard
            title={t("澄清状态")}
            status={activeResult?.answer.status}
            rows={[
              ["澄清", activeResult?.structured_task.clarification_status],
              ["问题", listText(activeResult?.structured_task.clarification_questions, t)],
              ["追问", listText(activeResult?.answer.follow_up_questions, t)]
            ]}
            t={t}
          />
          {activeResult?.structured_task.clarification_status === "needs_clarification" ? (
            <article className="process-card clarification-card">
              <div className="process-card-header">
                <h3>{t("澄清问题")}</h3>
                <span className="tag decision-ask">{displayLabel("ASK", t)}</span>
              </div>
              <p>{listText(activeResult.structured_task.clarification_questions, t)}</p>
              <div className="quick-actions">
                <button type="button" className="secondary-button" onClick={() => setQuestion(`${question}，时间范围按本月`)}>
                  {t("补充本月")}
                </button>
                <button type="button" className="ghost-button" onClick={() => setQuestion(`${question}，按市场维度`)}>
                  {t("补充市场维度")}
                </button>
              </div>
            </article>
          ) : null}
          <ProcessCard
            title={t("语义映射")}
            status={activeResult?.semantic_intent.permission_decision}
            rows={[
              ["指标", listText(activeResult?.semantic_intent.standard_metrics, t)],
              ["维度", listText(activeResult?.semantic_intent.standard_dimensions, t)],
              ["实体", listText(activeResult?.semantic_intent.entities, t)],
              ["数据源", listText(activeResult?.semantic_intent.data_sources, t)],
              ["备注", listText(activeResult?.semantic_intent.notes, t)]
            ]}
            t={t}
          />
          <ProcessCard
            title={t("执行计划")}
            status={activeResult?.execution_plan.tool_sequence.length ? "planned" : undefined}
            rows={[
              ["工具", listText(activeResult?.execution_plan.tool_sequence, t)],
              ["SQL", activeResult?.execution_plan.sql ?? t("无")],
              ["风险检查点", listText(activeResult?.execution_plan.risk_checkpoints, t)]
            ]}
            t={t}
          />
        </section>

        <section className="panel answer-panel">
          <div className="panel-toolbar">
            <div>
              <h3>{t("最终回答")}</h3>
              <p>{t("回答、证据、口径、限制和建议")}</p>
            </div>
            {activeResult ? <span className={statusClass(activeResult.answer.status)}>{displayLabel(activeResult.answer.status, t)}</span> : null}
          </div>
          <div className="answer-body">
            <div className="audience-strip">
              <strong>{t("受众视角")}</strong>
              <span>{t(audience === "manager" ? "管理者摘要版：先给结论和建议。" : audience === "data_team" ? "数据团队过程版：突出口径、SQL 摘要和 Trace。" : "运营明细版：突出可执行动作和明细限制。")}</span>
            </div>
            <strong>{activeResult?.answer.summary ?? t("运行一次 RMA 问数后展示答案")}</strong>
            <p>
              {t("指标口径：")}
              {activeResult?.answer.metric_definition ?? t("待运行")}
            </p>
            <p>
              {t("数据来源：")}
              {listText(activeResult?.answer.sources, t)}
            </p>
            <p>
              {t("限制说明：")}
              {listText(activeResult?.answer.limitations, t)}
            </p>
            <p>
              {t("建议：")}
              {listText(activeResult?.answer.suggestions, t)}
            </p>
            <div className="quick-actions">
              <button type="button" className="secondary-button" disabled={!activeResult?.execution_plan.sql} onClick={() => copyText(activeResult?.execution_plan.sql ?? "")}>
                {t("复制 SQL 摘要")}
              </button>
              <button type="button" className="secondary-button" disabled={!activeResult?.answer.audit_refs.length} onClick={() => copyText(activeResult?.answer.audit_refs.join(", ") ?? "")}>
                {t("复制审计引用")}
              </button>
              <button type="button" className="ghost-button" disabled={!activeResult} onClick={createCaseFromResult}>
                {t("一键转 Case")}
              </button>
            </div>
            {caseCreated ? <span className="tag status-bad_case_created">{t("已转入 Case / Bad Case 队列")}</span> : null}
            <details className="json-details">
              <summary>{t("证据详情")}</summary>
              <pre>{activeResult ? JSON.stringify(activeResult.answer.evidence, null, 2) : "safe evidence will appear here"}</pre>
            </details>
          </div>
        </section>

        <section className="panel feedback-panel">
          <div className="panel-toolbar">
            <div>
              <h3>{t("反馈 / Bad Case")}</h3>
              <p>{t("负反馈会进入 Bad Case 队列，用于 Case / Eval 回归")}</p>
            </div>
          </div>
          <div className="workbench-form">
            <label className="form-field">
              <span>{t("反馈")}</span>
              <select value={feedbackRating} onChange={(event) => setFeedbackRating(event.target.value as "positive" | "negative")}>
                <option value="positive">{t("满意")}</option>
                <option value="negative">{t("不满意 / 转 Bad Case")}</option>
              </select>
            </label>
            <label className="form-field">
              <span>{t("错误类型")}</span>
              <select value={errorType} onChange={(event) => setErrorType(event.target.value)}>
                <option value="metric_mismatch">{displayLabel("metric_mismatch", t)}</option>
                <option value="value_error">{displayLabel("value_error", t)}</option>
                <option value="permission_error">{displayLabel("permission_error", t)}</option>
                <option value="answer_unclear">{displayLabel("answer_unclear", t)}</option>
              </select>
            </label>
            <label className="form-field span-all">
              <span>{t("评论")}</span>
              <textarea value={comment} onChange={(event) => setComment(event.target.value)} />
            </label>
            <button type="button" className="primary-button span-all" onClick={submitFeedback} disabled={!result || feedbackLoading}>
              {feedbackLoading ? t("提交中...") : t("提交反馈")}
            </button>
          </div>
          <div className="feedback-summary">
            {feedback ? (
              <span className="tag status-bad_case_created">
                {t("反馈已保存：")}
                {displayLabel(feedback.feedback.rating, t)}
              </span>
            ) : null}
            {badCases ? (
              <span className="tag status-open">
                {t("Bad Case 队列：")}
                {badCases.count}
              </span>
            ) : null}
          </div>
        </section>
      </div>
    </section>
  );
}

function TimelineTrace({ values, t }: { values: string[]; t: Translate }) {
  if (!values.length) {
    return <TraceItem label={t("执行节点")} value={t("待运行")} />;
  }
  return (
    <div className="timeline-trace">
      {values.map((value, index) => (
        <div key={`${value}-${index}`} className="timeline-node">
          <span>{index + 1}</span>
          <strong>{displayLabel(value, t)}</strong>
        </div>
      ))}
    </div>
  );
}

function TraceItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="trace-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProcessCard({ title, status, rows, t }: { title: string; status?: string | null; rows: Array<[string, unknown]>; t: Translate }) {
  return (
    <article className="process-card">
      <div className="process-card-header">
        <h3>{title}</h3>
        {status ? <span className={statusClass(status)}>{displayLabel(status, t)}</span> : <span className="tag">{t("待运行")}</span>}
      </div>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{t(label)}</dt>
            <dd>{displayLabel(value ?? t("待运行"), t)}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}
