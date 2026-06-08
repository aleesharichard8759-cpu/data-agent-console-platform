import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function jsonResponse(payload: unknown, ok = true) {
  return {
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? "OK" : "Error",
    json: async () => payload
  } as Response;
}

const dataQARunResult = {
  request: { user_query: "本月 RMA 客诉率是多少？", audience: "manager" },
  structured_task: {
    task_id: "task-rma-1",
    task_type: "query_metric",
    task_level: "L1",
    metric: "客诉率",
    dimensions: ["市场"],
    time_range_label: "本月",
    clarification_status: "complete",
    clarification_questions: []
  },
  semantic_intent: {
    standard_metrics: ["rma_complaint_rate"],
    standard_dimensions: ["market"],
    entities: ["RMA"],
    data_sources: ["ads_rma_metric_1d"],
    permission_decision: "allow",
    notes: ["Runtime release bound"]
  },
  execution_plan: {
    tool_sequence: ["search_metadata", "query_sql"],
    sql: "select complaint_rate from ads_rma_metric_1d limit 20",
    risk_checkpoints: ["policy_engine", "sql_gateway", "dlp_masking", "audit"]
  },
  answer: {
    status: "complete",
    summary: "本月 RMA 客诉率为 2.3%。",
    evidence: [{ metric: "complaint_rate", value: 0.023 }],
    metric_definition: "客诉量 / 销售订单量",
    sources: ["sql_gateway_reviewed_query"],
    limitations: ["mock result"],
    suggestions: ["关注质量问题原因"],
    follow_up_questions: [],
    audit_refs: ["audit-1"]
  },
  trace: {
    trace_id: "trace-rma-1",
    nodes: ["request_intake", "semantic_mapping", "answer_synthesis"],
    tool_calls: ["search_metadata", "query_sql"],
    scores: { intent: 0.98 },
    failure_node: null
  }
};

function expandNavGroup(name: string) {
  const button = screen.getByRole("button", { name });
  if (button.getAttribute("aria-expanded") === "false") {
    fireEvent.click(button);
  }
}

describe("Data Agent Console MVP", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    window.location.hash = "/";
  });

  it("renders dashboard and navigates to Runtime pages", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Data Agent Console", level: 2 })).toBeInTheDocument();

    expandNavGroup("Runtime 配置中心+");
    fireEvent.click(screen.getByRole("button", { name: /SQL 网关/ }));
    expect(screen.getByRole("heading", { name: "SQL Gateway", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("禁止 DDL / DML")).toBeInTheDocument();
  });

  it("filters dashboard journeys by the selected role", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "接入一个新数据源", level: 3 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "配置 RMA 问数 Agent", level: 3 })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "验证 Agent 能否上线", level: 3 })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    fireEvent.change(screen.getByLabelText("当前角色"), { target: { value: "data_product_manager" } });

    const rmaJourney = screen.getByRole("heading", { name: "配置 RMA 问数 Agent", level: 3 }).closest("article");
    expect(rmaJourney).not.toBeNull();
    expect(screen.queryByRole("heading", { name: "接入一个新数据源", level: 3 })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "验证 Agent 能否上线", level: 3 })).not.toBeInTheDocument();
    expect(screen.getAllByText("RMA Agent 发布门禁").length).toBeGreaterThan(0);
    expect(screen.queryByText("StarRocks 只读源健康检查")).not.toBeInTheDocument();

    fireEvent.click(within(rmaJourney!).getByRole("button", { name: "开始" }));

    expect(screen.getByRole("heading", { name: "Data&QA Agent Apps", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("定义一个可发布的 Data&QA Agent 产品实例。")).toBeInTheDocument();
  });

  it("navigates to both usage workbenches from the sidebar without dashboard duplicate buttons", () => {
    render(<App />);

    expect(screen.queryByRole("button", { name: "打开 Runtime 工作台" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "打开问数工作台" })).not.toBeInTheDocument();
    expect(screen.queryByText("/runtime/workbench")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Runtime 工作台/ }));
    expect(screen.getByRole("heading", { name: "Runtime 使用工作台", level: 2 })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /首页看板/ }));
    fireEvent.click(screen.getByRole("button", { name: /问数工作台/ }));
    expect(screen.getByRole("heading", { name: "Agent Workspace", level: 2 })).toBeInTheDocument();
  });

  it("switches language from settings and shows template versions", () => {
    render(<App />);

    expect(screen.getByText("当前环境")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生产" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    expect(screen.getAllByText("0.00.1")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByText("Environment")).toBeInTheDocument();
    expect(screen.getByText("Home Overview")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prod" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect New Data Source" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "中文" }));
    expect(screen.getByText("当前环境")).toBeInTheDocument();
  });

  it("runs the Runtime safety simulator through Mock API", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/api/sql/review")) {
        return jsonResponse({
          trace_id: "trace-sql-1",
          audit_refs: ["audit-sql-1"],
          allowed: false,
          decision: "deny",
          risks: [{ risk_type: "select_star", severity: "high" }],
          rewritten_sql: null,
          reason: "SELECT * is blocked.",
          required_approval: false
        });
      }
      if (url.includes("/api/tools/query_sql/dry-run")) {
        return jsonResponse({
          trace_id: "trace-tool-1",
          audit_refs: ["audit-tool-1"],
          tool_name: "query_sql",
          status: "denied",
          result: {
            status: "denied",
            output: { policy_decision: "deny" },
            error_message: "Blocked by SQL Gateway.",
            masked_fields: []
          }
        });
      }
      return jsonResponse({ events: [{ event_id: "audit-1", action: "sql.review", outcome: "deny" }] });
    });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Runtime 工作台/ }));
    fireEvent.click(screen.getByRole("button", { name: "运行安全模拟" }));

    expect(await screen.findByText("SELECT * is blocked.")).toBeInTheDocument();
    expect(screen.getAllByText("策略引擎").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SQL 网关").length).toBeGreaterThan(0);
    expect(screen.getAllByText("DLP / 脱敏").length).toBeGreaterThan(0);
    expect(screen.getAllByText("审计事件").length).toBeGreaterThan(0);
  });

  it("runs a governance job and shows Plan Mode approval", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/tasks")) {
        return jsonResponse({
          task_id: "task-1",
          trace_id: "trace-task-1",
          audit_refs: ["audit-task-1"],
          status: "created",
          task_type: "sensitivity_scan",
          task_level: "G4"
        });
      }
      if (url.includes("/api/tasks/task-1/run")) {
        return jsonResponse({
          task_id: "task-1",
          trace_id: "trace-run-1",
          audit_refs: ["audit-run-1"],
          status: "plan_required",
          executed_nodes: ["task_intake", "governance_planning"],
          required_approvals: [{ plan_id: "plan-1", risk_level: "G4", required_approvers: ["mock_security_reviewer"] }],
          final_response: "Approval required."
        });
      }
      return jsonResponse({ events: [{ event_id: "audit-job-1", action: "plan.create", outcome: "ask" }] });
    });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Runtime 工作台/ }));
    fireEvent.click(screen.getByRole("button", { name: "治理作业台" }));
    fireEvent.click(screen.getByRole("button", { name: "运行治理作业" }));

    expect(await screen.findByText("高风险治理计划需要审批")).toBeInTheDocument();
    expect(screen.getAllByText(/plan-1/).length).toBeGreaterThan(0);
  });

  it("runs Data&QA workspace and routes negative feedback to Bad Case", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/data-qa/run")) return jsonResponse(dataQARunResult);
      if (url.includes("/api/data-qa/tasks/task-rma-1")) return jsonResponse({ result: dataQARunResult });
      if (url.endsWith("/api/data-qa/feedback")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as { rating: string };
        return jsonResponse({
          feedback: {
            feedback_id: "feedback-1",
            rating: body.rating,
            error_type: "metric_mismatch",
            enter_bad_case: body.rating === "negative"
          }
        });
      }
      return jsonResponse({ count: 1, bad_cases: [{ feedback_id: "feedback-1", error_type: "metric_mismatch" }] });
    });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /问数工作台/ }));
    fireEvent.click(screen.getByRole("button", { name: "运行问数分析" }));

    expect(await screen.findByText("本月 RMA 客诉率为 2.3%。")).toBeInTheDocument();
    expect(screen.getByText("指标查询")).toBeInTheDocument();
    expect(screen.getAllByText(/元数据检索工具, SQL 查询工具/).length).toBeGreaterThan(0);
    expect(screen.getByText("trace-rma-1")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("反馈"), { target: { value: "negative" } });
    fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));

    expect(await screen.findByText("Bad Case 队列：1")).toBeInTheDocument();
  });

  it("keeps observability pages read-only", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /链路追踪 \/ 审计日志/ }));

    expect(screen.getByRole("heading", { name: "Trace / Audit Logs", level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新增审计备注" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "查看" }).length).toBeGreaterThan(0);
  });

  it("opens and closes create modal", () => {
    render(<App />);

    expandNavGroup("Data&QA 产品配置+");
    fireEvent.click(screen.getByRole("button", { name: "Agent 应用" }));
    fireEvent.click(screen.getByRole("button", { name: "新建 Agent" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("saves local mock state from a modal", () => {
    render(<App />);

    expandNavGroup("Data&QA 产品配置+");
    fireEvent.click(screen.getByRole("button", { name: /语义层/ }));
    fireEvent.click(screen.getByRole("button", { name: "新增语义对象" }));
    fireEvent.change(screen.getByLabelText("名称"), { target: { value: "退货率" } });
    fireEvent.change(screen.getByLabelText("业务定义"), { target: { value: "退货量 / 销售订单量" } });
    fireEvent.change(screen.getByLabelText("字段映射"), { target: { value: "return_count / sales_order_count" } });
    fireEvent.change(screen.getByLabelText("负责人"), { target: { value: "数据分析师" } });
    fireEvent.click(screen.getByRole("button", { name: "保存到 mock state" }));

    expect(screen.getByText("退货率")).toBeInTheDocument();
  });
});
