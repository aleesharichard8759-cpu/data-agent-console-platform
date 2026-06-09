from __future__ import annotations

from typing import Any

from app.audit import AuditLogger
from app.data_qa.models import (
    AgentAnswer,
    AudienceRole,
    ClarificationStatus,
    DataQARunResult,
    DataQATaskLevel,
    DataQATaskRequest,
    DataQATaskType,
    ExecutionPlan,
    SemanticIntent,
    StructuredTask,
    TraceRecord,
)
from app.domain.assets import DataDomain
from app.domain.identity import UserContext
from app.domain.policy import PolicyDecision
from app.domain.tools import ToolCallRequest, ToolExecutionStatus, ToolRiskLevel
from app.policy import PolicyEngine
from app.tools import DataToolRegistry, ToolExecutionContext


class DataQAOrchestrator:
    """Deterministic Data&QA product-layer loop for the MVP.

    It does not call an LLM or production database. Data lookup is routed through
    governed DataTool calls so the product layer preserves runtime safety boundaries.
    """

    RMA_ADS_TABLE = "ads_afs_rma_multi_dim_metric_1d"
    RMA_TIME_FIELD = "stat_date"

    workflow_nodes: tuple[str, ...] = (
        "request_intake",
        "task_identification",
        "clarification",
        "semantic_mapping",
        "execution_planning",
        "analysis_execution",
        "answer_synthesis",
        "risk_review",
        "feedback_persistence",
    )

    def __init__(
        self,
        *,
        policy_engine: PolicyEngine,
        tool_registry: DataToolRegistry,
        audit_logger: AuditLogger,
    ) -> None:
        self.policy_engine = policy_engine
        self.tool_registry = tool_registry
        self.audit_logger = audit_logger

    def run(
        self,
        request: DataQATaskRequest,
        *,
        user_context: UserContext,
        session_id: str | None,
    ) -> DataQARunResult:
        start_index = len(self.audit_logger.list_events())
        structured_task = self.structure_task(request)
        semantic_intent = self.map_semantic_intent(structured_task, request)
        execution_plan = self.plan_execution(structured_task, semantic_intent)
        evidence, tool_calls = self.execute_plan(
            structured_task,
            execution_plan,
            user_context=user_context,
            session_id=session_id,
        )
        audit_refs = tuple(
            str(event.event_id) for event in self.audit_logger.list_events()[start_index:]
        )
        answer = self.synthesize_answer(
            request,
            structured_task,
            semantic_intent,
            execution_plan,
            evidence,
            audit_refs,
        )
        trace = TraceRecord(
            task_id=structured_task.task_id,
            nodes=self.workflow_nodes,
            tool_calls=tool_calls,
            scores=self._scores_for(structured_task, semantic_intent, answer),
            failure_node=self._failure_node(structured_task, semantic_intent, answer),
        )
        return DataQARunResult(
            request=request,
            structured_task=structured_task,
            semantic_intent=semantic_intent,
            execution_plan=execution_plan,
            answer=answer,
            trace=trace,
        )

    def structure_task(self, request: DataQATaskRequest) -> StructuredTask:
        query = request.user_query.strip()
        task_type = self._task_type(query)
        task_level = self._task_level(task_type)
        metric = self._metric(query)
        dimensions = self._dimensions(query)
        time_range = self._time_range(query)
        filters = self._filters(query, request.business_domain)
        clarification_questions = self._clarification_questions(
            query,
            task_type,
            metric,
            time_range,
        )
        escalation_reason = self._escalation_reason(query, task_type)
        if escalation_reason is not None:
            status = ClarificationStatus.ESCALATED
        elif clarification_questions:
            status = ClarificationStatus.NEEDS_CLARIFICATION
        else:
            status = ClarificationStatus.COMPLETE
        return StructuredTask(
            task_type=task_type,
            task_level=task_level,
            raw_query=query,
            metric=metric,
            dimensions=dimensions,
            time_range_label=time_range,
            filters=filters,
            comparison=self._comparison(query),
            clarification_status=status,
            clarification_questions=clarification_questions,
            requires_human_escalation=escalation_reason is not None,
            escalation_reason=escalation_reason,
        )

    def map_semantic_intent(
        self,
        task: StructuredTask,
        request: DataQATaskRequest,
    ) -> SemanticIntent:
        metric = task.metric or "待确认"
        data_sources = self._data_sources_for(task, request.business_domain)
        permission_decision = PolicyDecision.ALLOW
        notes: list[str] = []
        if self._contains_sensitive_intent(task.raw_query):
            permission_decision = PolicyDecision.DENY
            notes.append("AI 禁止访问明文个人信息、密钥、原始 ODS 或未治理资产。")
        elif task.requires_human_escalation:
            permission_decision = PolicyDecision.ASK
            notes.append("L2+ 或高风险经营问题需要人工复核后继续。")
        if task.clarification_status == ClarificationStatus.NEEDS_CLARIFICATION:
            notes.append("口径不完整，必须澄清后再执行取数。")
        return SemanticIntent(
            task_id=task.task_id,
            standard_metrics=(metric,) if metric != "待确认" else tuple(),
            standard_dimensions=task.dimensions,
            entities=task.filters,
            knowledge_refs=self._knowledge_refs_for(task),
            data_sources=data_sources,
            permission_decision=permission_decision,
            temporary_metric=metric == "待确认",
            notes=tuple(notes),
        )

    def plan_execution(self, task: StructuredTask, intent: SemanticIntent) -> ExecutionPlan:
        if intent.permission_decision == PolicyDecision.DENY:
            return ExecutionPlan(
                task_id=task.task_id,
                tool_sequence=tuple(),
                risk_checkpoints=("deny_sensitive_or_secret_request",),
            )
        if task.clarification_status != ClarificationStatus.COMPLETE:
            return ExecutionPlan(
                task_id=task.task_id,
                tool_sequence=tuple(),
                knowledge_queries=intent.knowledge_refs,
                risk_checkpoints=("clarification_required", "human_escalation_review"),
            )
        if task.task_type in {DataQATaskType.EXPLAIN_METRIC, DataQATaskType.KNOWLEDGE_QA}:
            return ExecutionPlan(
                task_id=task.task_id,
                tool_sequence=("get_metric_definition",)
                if task.task_type == DataQATaskType.EXPLAIN_METRIC
                else tuple(),
                knowledge_queries=intent.knowledge_refs,
                risk_checkpoints=("metric_definition_consistency", "source_citation_required"),
            )
        return ExecutionPlan(
            task_id=task.task_id,
            tool_sequence=("search_metadata", "query_sql"),
            sql=self._sql_for(task, intent),
            knowledge_queries=intent.knowledge_refs,
            risk_checkpoints=(
                "policy_engine",
                "sql_gateway",
                "dlp_masking",
                "audit_trace",
                "answer_limitations",
            ),
        )

    def execute_plan(
        self,
        task: StructuredTask,
        plan: ExecutionPlan,
        *,
        user_context: UserContext,
        session_id: str | None,
    ) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
        if task.clarification_status != ClarificationStatus.COMPLETE:
            return tuple(), tuple()
        evidence: list[dict[str, Any]] = []
        tool_calls: list[str] = []
        for tool_name in plan.tool_sequence:
            tool_calls.append(tool_name)
            request = self._tool_request(tool_name, task, plan)
            result = self.tool_registry.execute_tool(
                request,
                ToolExecutionContext(
                    user_context=user_context,
                    task_context=None,
                    policy_engine=self.policy_engine,
                    audit_logger=self.audit_logger,
                    dry_run=True,
                    plan_mode=False,
                    session_id=session_id,
                    agent_name="data_qa_orchestrator",
                ),
            )
            evidence.append(
                {
                    "tool": tool_name,
                    "status": result.status.value,
                    "output": result.output,
                    "error_message": result.error_message,
                }
            )
            if result.status in {ToolExecutionStatus.DENIED, ToolExecutionStatus.ASKED}:
                break
        if plan.knowledge_queries:
            evidence.append(
                {
                    "tool": "knowledge_base",
                    "status": "succeeded",
                    "output": {
                        "data": {
                            "entries": [
                                self._knowledge_entry(query) for query in plan.knowledge_queries
                            ]
                        }
                    },
                    "error_message": None,
                }
            )
        return tuple(evidence), tuple(tool_calls)

    def synthesize_answer(
        self,
        request: DataQATaskRequest,
        task: StructuredTask,
        intent: SemanticIntent,
        plan: ExecutionPlan,
        evidence: tuple[dict[str, Any], ...],
        audit_refs: tuple[str, ...],
    ) -> AgentAnswer:
        if intent.permission_decision == PolicyDecision.DENY:
            return AgentAnswer(
                task_id=task.task_id,
                status=ClarificationStatus.DENIED,
                summary=(
                    "该问题涉及敏感数据、密钥、原始明细或未授权资产，"
                    "Data&QA Agent 不能直接回答。"
                ),
                limitations=("默认拒绝、最小权限、按需授权、全程审计。",),
                suggestions=("请提交明确的数据对象、用途、范围和审批信息后转人工复核。",),
                requires_human_escalation=True,
                audit_refs=audit_refs,
            )
        if task.clarification_status == ClarificationStatus.NEEDS_CLARIFICATION:
            return AgentAnswer(
                task_id=task.task_id,
                status=ClarificationStatus.NEEDS_CLARIFICATION,
                summary="当前问题缺少必要口径，先澄清后再取数，避免直接生成不可复核结论。",
                sources=intent.data_sources,
                limitations=("未澄清的问题不执行 SQL。",),
                follow_up_questions=task.clarification_questions,
                audit_refs=audit_refs,
            )
        if task.clarification_status == ClarificationStatus.ESCALATED:
            return AgentAnswer(
                task_id=task.task_id,
                status=ClarificationStatus.ESCALATED,
                summary="该问题已识别为 L2+ 或高风险业务建议场景，MVP 仅提供边界识别和人工升级。",
                sources=intent.data_sources,
                limitations=(task.escalation_reason or "需要人工复核。",),
                suggestions=("由数据团队补充诊断路径、业务假设和可验证证据后继续。",),
                requires_human_escalation=True,
                audit_refs=audit_refs,
            )
        summary = self._summary_for(request.audience, task, evidence)
        return AgentAnswer(
            task_id=task.task_id,
            status=ClarificationStatus.COMPLETE,
            summary=summary,
            evidence=evidence,
            metric_definition=self._metric_definition_for(task),
            sources=self._sources_for(intent, plan),
            limitations=self._limitations_for(task, intent),
            suggestions=self._suggestions_for(request.audience, task),
            audit_refs=audit_refs,
        )

    @staticmethod
    def _task_type(query: str) -> DataQATaskType:
        lowered = query.lower()
        if any(token in query for token in ("报价", "调价", "加预算", "投放", "触达", "执行")):
            return DataQATaskType.BUSINESS_ADVICE
        if any(token in query for token in ("归因", "主要受哪些因素", "受哪些因素")):
            return DataQATaskType.ATTRIBUTION_ANALYSIS
        if any(token in query for token in ("为什么", "异常", "下降", "变差", "波动")):
            return DataQATaskType.ANOMALY_DIAGNOSIS
        if any(token in query for token in ("是什么", "定义", "口径", "公式")):
            return DataQATaskType.EXPLAIN_METRIC
        if any(token in query for token in ("怎么用", "流程", "制度", "权限申请", "系统使用")):
            return DataQATaskType.KNOWLEDGE_QA
        if "faq" in lowered or "knowledge" in lowered:
            return DataQATaskType.KNOWLEDGE_QA
        return DataQATaskType.QUERY_METRIC

    @staticmethod
    def _task_level(task_type: DataQATaskType) -> DataQATaskLevel:
        if task_type in {
            DataQATaskType.QUERY_METRIC,
            DataQATaskType.EXPLAIN_METRIC,
            DataQATaskType.KNOWLEDGE_QA,
            DataQATaskType.MIXED,
        }:
            return DataQATaskLevel.L1
        if task_type == DataQATaskType.ANOMALY_DIAGNOSIS:
            return DataQATaskLevel.L2
        if task_type == DataQATaskType.ATTRIBUTION_ANALYSIS:
            return DataQATaskLevel.L3
        return DataQATaskLevel.L4

    @staticmethod
    def _metric(query: str) -> str | None:
        if "其他收入" in query:
            return "other_income"
        if any(token in query for token in ("收入", "销售额", "GMV", "gmv")):
            return "order_amount"
        if "订单" in query:
            return "order_count"
        if "转化" in query:
            return "conversion_rate"
        if "客诉率" in query:
            return "complaint_rate"
        return None

    @staticmethod
    def _dimensions(query: str) -> tuple[str, ...]:
        dimensions: list[str] = []
        if "市场" in query:
            dimensions.append("market")
        if "渠道" in query:
            dimensions.append("channel")
        if "客户" in query:
            dimensions.append("customer_segment")
        if "SKU" in query.upper() or "商品" in query:
            dimensions.append("sku")
        return tuple(dimensions)

    @staticmethod
    def _time_range(query: str) -> str | None:
        if "上个月" in query:
            return "last_month"
        if "本月" in query or "这个月" in query:
            return "current_month"
        if "全年" in query or "今年" in query:
            return "current_year"
        if "昨天" in query:
            return "yesterday"
        if "最近" in query:
            return None
        return None

    @staticmethod
    def _filters(query: str, business_domain: DataDomain) -> tuple[str, ...]:
        filters: list[str] = []
        if "华东" in query:
            filters.append("region=华东")
        if "欧洲" in query:
            filters.append("market=欧洲")
        if business_domain != DataDomain.UNKNOWN:
            filters.append(f"domain={business_domain.value}")
        return tuple(filters)

    @staticmethod
    def _comparison(query: str) -> str | None:
        if "环比" in query:
            return "mom"
        if "同比" in query:
            return "yoy"
        if "对比" in query:
            return "comparison"
        return None

    @staticmethod
    def _clarification_questions(
        query: str,
        task_type: DataQATaskType,
        metric: str | None,
        time_range: str | None,
    ) -> tuple[str, ...]:
        if task_type not in {DataQATaskType.QUERY_METRIC, DataQATaskType.MIXED}:
            return tuple()
        questions: list[str] = []
        if metric is None:
            questions.append("请确认要查询的指标，例如收入、订单数、转化率或客诉率。")
        if time_range is None:
            questions.append("请确认统计时间范围，例如上个月、本月、今年或具体日期。")
        if "最近" in query and time_range is None:
            questions.append("“最近”需要明确为自然月、滚动 7 天、滚动 30 天或其他周期。")
        return tuple(dict.fromkeys(questions))

    @staticmethod
    def _escalation_reason(query: str, task_type: DataQATaskType) -> str | None:
        if task_type == DataQATaskType.ANOMALY_DIAGNOSIS:
            return "L2 异常诊断需要标准诊断模板和人工复核，MVP 不自动给出归因结论。"
        if task_type == DataQATaskType.ATTRIBUTION_ANALYSIS:
            return "L3 归因分析需要证据链、假设检验和领域专家确认。"
        if task_type == DataQATaskType.BUSINESS_ADVICE:
            return "涉及投放、报价、触达或经营动作，系统只提供证据，不自动决策或执行。"
        if any(token in query.lower() for token in ("api key", "password", "token", "secret")):
            return "密钥和凭证类问题禁止进入模型上下文。"
        return None

    @staticmethod
    def _data_sources_for(task: StructuredTask, business_domain: DataDomain) -> tuple[str, ...]:
        if task.task_type == DataQATaskType.KNOWLEDGE_QA:
            return ("knowledge_base",)
        is_rma_query = (
            task.metric in {"complaint_rate", "problem_quantity"}
            or "rma" in task.raw_query.lower()
            or "客诉" in task.raw_query
        )
        if is_rma_query:
            return (DataQAOrchestrator.RMA_ADS_TABLE, "starrocks_information_schema")
        if business_domain == DataDomain.FINANCE:
            return ("ads_trade_order_dashboard_day", "metric_platform")
        return ("ads_trade_order_dashboard_day", "openmetadata", "metric_platform")

    @staticmethod
    def _knowledge_refs_for(task: StructuredTask) -> tuple[str, ...]:
        if task.task_type == DataQATaskType.KNOWLEDGE_QA:
            return ("data_qa_usage_policy",)
        if task.task_type == DataQATaskType.EXPLAIN_METRIC and task.metric:
            return (f"metric_definition:{task.metric}",)
        return tuple()

    @staticmethod
    def _contains_sensitive_intent(query: str) -> bool:
        lowered = query.lower()
        return any(
            token in lowered
            for token in (
                "手机号",
                "邮箱",
                "地址",
                "明文",
                "api key",
                "password",
                "token",
                "secret",
                "ods",
                "绕过",
            )
        )

    @staticmethod
    def _sql_for(task: StructuredTask, intent: SemanticIntent) -> str:
        metric = (intent.standard_metrics[0] if intent.standard_metrics else "order_count")
        if metric == "complaint_rate":
            return DataQAOrchestrator._rma_metric_sql(
                metric_expr=(
                    "sum(problem_qty) / nullif(sum(sale_qty), 0)"
                ),
                alias="complaint_rate",
                task=task,
            )
        if metric in {"problem_quantity", "rma_problem_quantity"}:
            return DataQAOrchestrator._rma_metric_sql(
                metric_expr="sum(problem_qty)",
                alias="problem_quantity",
                task=task,
            )
        metric_expr = "count(order_id)" if metric == "order_count" else "sum(order_amount)"
        alias = "order_count" if metric == "order_count" else metric
        group_by = ", market" if "market" in task.dimensions else ""
        select_dimensions = "metric_date" + group_by
        time_filter = (
            f"metric_date = '{task.time_range_label}'"
            if task.time_range_label
            else "metric_date = current_date()"
        )
        return (
            f"select {select_dimensions}, {metric_expr} as {alias} "
            "from ads_trade_order_dashboard_day "
            f"where {time_filter} "
            f"group by {select_dimensions} limit 100"
        )

    @staticmethod
    def _rma_metric_sql(metric_expr: str, alias: str, task: StructuredTask) -> str:
        select_dimensions = ""
        group_by_fields: list[str] = []
        if "market" in task.dimensions:
            select_dimensions = "market, "
            group_by_fields.append("market")
        time_filter = DataQAOrchestrator._rma_time_filter(task.time_range_label)
        group_by_clause = f" group by {', '.join(group_by_fields)}" if group_by_fields else ""
        return (
            f"select {select_dimensions}{metric_expr} as {alias} "
            f"from {DataQAOrchestrator.RMA_ADS_TABLE} "
            f"where {time_filter}{group_by_clause} limit 100"
        )

    @staticmethod
    def _rma_time_filter(time_range_label: str | None) -> str:
        field = DataQAOrchestrator.RMA_TIME_FIELD
        if time_range_label == "current_month":
            return f"date_trunc('month', {field}) = date_trunc('month', current_date())"
        if time_range_label == "last_month":
            return (
                f"{field} >= date_trunc('month', date_sub(current_date(), interval 1 month)) "
                f"and {field} < date_trunc('month', current_date())"
            )
        if time_range_label == "current_year":
            return f"date_trunc('year', {field}) = date_trunc('year', current_date())"
        if time_range_label == "yesterday":
            return f"{field} = date_sub(current_date(), interval 1 day)"
        return f"{field} = current_date()"

    def _tool_request(
        self,
        tool_name: str,
        task: StructuredTask,
        plan: ExecutionPlan,
    ) -> ToolCallRequest:
        if tool_name == "search_metadata":
            return ToolCallRequest(
                tool_name="search_metadata",
                action="metadata.query",
                asset_type="metadata",
                parameters={
                    "query": "rma"
                    if task.metric in {"complaint_rate", "problem_quantity"}
                    else "order",
                    "limit": 5,
                },
                risk_level=ToolRiskLevel.LOW,
            )
        if tool_name == "get_metric_definition":
            return ToolCallRequest(
                tool_name="get_metric_definition",
                action="metric.definition.query",
                asset_type="metric_definition",
                parameters={"metric_name": task.metric or "unknown_metric"},
                risk_level=ToolRiskLevel.LOW,
            )
        return ToolCallRequest(
            tool_name="query_sql",
            action="sql.query",
            asset_type="sql_query",
            parameters={
                "sql": plan.sql
                or (
                    f"select {DataQAOrchestrator.RMA_TIME_FIELD}, "
                    "sum(problem_qty) / nullif(sum(sale_qty), 0) as complaint_rate "
                    f"from {DataQAOrchestrator.RMA_ADS_TABLE} "
                    f"group by {DataQAOrchestrator.RMA_TIME_FIELD} limit 100"
                )
            },
            risk_level=ToolRiskLevel.LOW,
            requires_sql_gateway=True,
        )

    @staticmethod
    def _knowledge_entry(query: str) -> dict[str, str]:
        if query == "data_qa_usage_policy":
            return {
                "ref": query,
                "title": "Data&QA 使用边界",
                "summary": (
                    "先澄清口径，再执行取数；敏感明细、密钥、原始 ODS "
                    "和未治理资产默认不可查。"
                ),
            }
        return {
            "ref": query,
            "title": "指标口径说明",
            "summary": "指标需包含业务定义、技术口径、统计周期、数据来源和适用边界。",
        }

    @staticmethod
    def _summary_for(
        audience: AudienceRole,
        task: StructuredTask,
        evidence: tuple[dict[str, Any], ...],
    ) -> str:
        metric = task.metric or "指标"
        if task.task_type == DataQATaskType.EXPLAIN_METRIC:
            return f"{metric} 的口径已按指标字典返回，回答包含业务定义、技术口径和待确认边界。"
        if task.task_type == DataQATaskType.KNOWLEDGE_QA:
            return "已按知识库边界回答，并标明规则来源和限制条件。"
        succeeded = any(item.get("status") == "succeeded" for item in evidence)
        prefix = "管理摘要：" if audience == AudienceRole.MANAGER else ""
        value_summary = DataQAOrchestrator._metric_value_summary(task, evidence)
        if value_summary:
            return f"{prefix}{value_summary}，口径、来源和审计轨迹已记录。"
        status = "已完成受治理的 L1 查询" if succeeded else "查询未完成，需要复核工具结果"
        return f"{prefix}{status}，指标为 {metric}，结果包含口径、来源、限制条件和审计轨迹。"

    @staticmethod
    def _metric_definition_for(task: StructuredTask) -> str | None:
        if task.metric is None:
            return None
        if task.metric == "complaint_rate":
            return (
                "客诉率 = SUM(problem_qty) / NULLIF(SUM(sale_qty), 0)，"
                "来源表 ads_afs_rma_multi_dim_metric_1d，默认时间字段 stat_date。"
            )
        return (
            f"{task.metric} 使用治理后的标准指标口径；如需从明细临时计算，"
            "必须显式标记为临时分析口径。"
        )

    @staticmethod
    def _metric_value_summary(
        task: StructuredTask,
        evidence: tuple[dict[str, Any], ...],
    ) -> str | None:
        if task.metric is None:
            return None
        for item in evidence:
            if item.get("tool") != "query_sql" or item.get("status") != "succeeded":
                continue
            data = item.get("output", {}).get("data", {})
            rows = data.get("rows", [])
            if not rows:
                continue
            row = rows[0]
            if task.metric == "complaint_rate" and "complaint_rate" in row:
                value = row["complaint_rate"]
                try:
                    return f"{task.time_range_label or '当前周期'} RMA 客诉率为 {float(value) * 100:.2f}%"
                except (TypeError, ValueError):
                    return f"{task.time_range_label or '当前周期'} RMA 客诉率为 {value}"
            if task.metric in row:
                return f"{task.time_range_label or '当前周期'} {task.metric} 为 {row[task.metric]}"
        return None

    @staticmethod
    def _sources_for(intent: SemanticIntent, plan: ExecutionPlan) -> tuple[str, ...]:
        sources = list(intent.data_sources)
        if plan.sql:
            sources.append("sql_gateway_reviewed_query")
        return tuple(dict.fromkeys(sources))

    @staticmethod
    def _limitations_for(task: StructuredTask, intent: SemanticIntent) -> tuple[str, ...]:
        limitations = [
            "MVP 仅稳定承诺 L1 查询取数、指标解释和知识库解释。",
            "所有数据访问必须通过 Runtime DataTool、Policy Engine、SQL Gateway、DLP 和 Audit。",
        ]
        if intent.temporary_metric:
            limitations.append("当前指标未完全映射到标准语义层，需标记为待确认。")
        if task.metric == "gross_profit":
            limitations.append("毛利等高敏经营指标需要按权限范围展示。")
        return tuple(limitations)

    @staticmethod
    def _suggestions_for(audience: AudienceRole, task: StructuredTask) -> tuple[str, ...]:
        if audience == AudienceRole.MANAGER:
            return ("仅将结果作为经营辅助证据，高风险动作需业务负责人确认。",)
        if audience == AudienceRole.OPERATIONS:
            return ("可继续补充市场、渠道、SKU 等筛选条件获取更细分结果。",)
        return ("数据团队可查看结构化任务、SQL、工具轨迹和评测 Case 以复核。",)

    @staticmethod
    def _scores_for(
        task: StructuredTask,
        intent: SemanticIntent,
        answer: AgentAnswer,
    ) -> dict[str, float]:
        return {
            "intent_identification": 1.0 if task.task_type else 0.0,
            "metric_mapping": (
                1.0
                if intent.standard_metrics or task.task_type == DataQATaskType.KNOWLEDGE_QA
                else 0.5
            ),
            "clarification_quality": (
                1.0
                if answer.status != ClarificationStatus.COMPLETE or task.time_range_label
                else 0.8
            ),
            "answer_traceability": 1.0 if answer.sources or answer.audit_refs else 0.6,
        }

    @staticmethod
    def _failure_node(
        task: StructuredTask,
        intent: SemanticIntent,
        answer: AgentAnswer,
    ) -> str | None:
        del intent
        if answer.status == ClarificationStatus.DENIED:
            return "risk_review"
        if task.clarification_status == ClarificationStatus.NEEDS_CLARIFICATION:
            return "clarification"
        if task.requires_human_escalation:
            return "risk_review"
        return None
