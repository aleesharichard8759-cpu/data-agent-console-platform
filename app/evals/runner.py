from __future__ import annotations

import json

from app.agents import build_default_agent_registry
from app.audit import InMemoryAuditLogger
from app.domain.identity import UserContext, UserRole
from app.domain.policy import PolicyDecision
from app.domain.tools import ToolCallRequest, ToolExecutionStatus, ToolRiskLevel
from app.evals.graders import BaseGrader, default_graders
from app.evals.models import EvalCase, EvalCaseResult, EvalObservation, EvalReport
from app.policy import PolicyEngine
from app.runtime import GovernanceEngine, TaskRunStatus
from app.tools import QuerySQLTool, ToolExecutionContext


class EvalRunner:
    def __init__(
        self,
        *,
        graders: tuple[BaseGrader, ...] | None = None,
        user_context: UserContext | None = None,
    ) -> None:
        self.graders = graders or default_graders()
        self.user_context = user_context or UserContext(
            user_id="eval_user",
            display_name="Eval User",
            roles=(UserRole.DATA_STEWARD,),
        )
        self._last_results: tuple[EvalCaseResult, ...] = tuple()

    def run_case(self, case: EvalCase) -> EvalCaseResult:
        audit_logger = InMemoryAuditLogger()
        policy_engine = PolicyEngine()
        engine = GovernanceEngine(policy_engine=policy_engine, audit_logger=audit_logger)
        engine.start_session(self.user_context)
        task = engine.create_task(case.user_query)
        selected_agents = tuple(
            agent.name
            for agent in build_default_agent_registry(
                policy_engine=policy_engine,
                audit_logger=audit_logger,
            ).select_agents_for_task(task)
        )
        task_result = engine.run_task(task.task_id)
        policy_decision, probe_tools, probe_summary = self._probe_policy(case, policy_engine)
        if policy_decision is None:
            policy_decision = (
                PolicyDecision.ASK
                if task_result.status == TaskRunStatus.WAITING_APPROVAL
                else PolicyDecision.ALLOW
            )
        audit_tools = tuple(
            item
            for event in audit_logger.list_events()
            for item in (event.tool_name, event.action)
            if isinstance(item, str)
        )
        planned_tools = tuple(
            tool
            for agent in build_default_agent_registry(
                policy_engine=policy_engine,
                audit_logger=audit_logger,
            ).select_agents_for_task(task)
            for tool in agent.allowed_tools
            if task_result.status == TaskRunStatus.WAITING_APPROVAL
        )
        used_tools = tuple(dict.fromkeys((*audit_tools, *planned_tools, *probe_tools)))
        structured = {
            "task_type": task.task_type.value,
            "task_level": task.task_level.value,
            "task_status": task_result.status.value,
            "selected_agents": selected_agents,
            "used_tools": used_tools,
            "recommendations": task_result.recommendations,
            "required_approvals": task_result.required_approvals,
            "policy_decision": policy_decision.value,
            "policy_probe": probe_summary,
        }
        observation = EvalObservation(
            case_id=case.case_id,
            classified_task_type=task.task_type,
            classified_task_level=task.task_level,
            selected_agents=selected_agents,
            used_tools=used_tools,
            policy_decision=policy_decision,
            task_status=task_result.status.value,
            output_text=json.dumps(structured, ensure_ascii=False, sort_keys=True),
            structured=structured,
        )
        grader_results = tuple(grader.grade(case, observation) for grader in self.graders)
        score = sum(result.score for result in grader_results) / len(grader_results)
        return EvalCaseResult(
            case_id=case.case_id,
            name=case.name,
            passed=all(result.passed for result in grader_results),
            score=score,
            grader_results=grader_results,
            observation=observation,
        )

    def run_suite(self, cases: tuple[EvalCase, ...]) -> tuple[EvalCaseResult, ...]:
        self._last_results = tuple(self.run_case(case) for case in cases)
        return self._last_results

    def produce_report(
        self,
        results: tuple[EvalCaseResult, ...] | None = None,
    ) -> EvalReport:
        resolved_results = results or self._last_results
        passed_cases = sum(1 for result in resolved_results if result.passed)
        total_cases = len(resolved_results)
        return EvalReport(
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=total_cases - passed_cases,
            pass_rate=passed_cases / total_cases if total_cases else 0.0,
            case_results=resolved_results,
        )

    def _probe_policy(
        self,
        case: EvalCase,
        policy_engine: PolicyEngine,
    ) -> tuple[PolicyDecision | None, tuple[str, ...], dict[str, object]]:
        query = case.user_query.lower()
        if "删除" in case.user_query:
            return self._evaluate_policy_request(policy_engine, "data.delete", "delete_data")
        if "关闭审计" in case.user_query:
            return self._evaluate_policy_request(policy_engine, "audit.disable", "audit")
        if "绕过 dlp" in query:
            return self._evaluate_policy_request(policy_engine, "dlp.bypass", "dlp")
        if "绕过脱敏" in case.user_query:
            return self._evaluate_policy_request(policy_engine, "masking.bypass", "masking")
        sql = self._sql_probe_for_query(case.user_query)
        if sql is not None:
            tool = QuerySQLTool()
            result = tool.execute(
                ToolCallRequest(
                    tool_name="query_sql",
                    action="sql.query",
                    asset_type="table",
                    parameters={"sql": sql},
                    risk_level=ToolRiskLevel.LOW,
                    requires_sql_gateway=True,
                ),
                ToolExecutionContext(
                    user_context=self.user_context,
                    task_context=None,
                    policy_engine=policy_engine,
                    audit_logger=InMemoryAuditLogger(),
                    dry_run=True,
                    agent_name="eval_runner",
                ),
            )
            decision = self._decision_from_tool_status(result.status)
            return (
                decision,
                ("query_sql", "sql.query"),
                {
                    "tool": "query_sql",
                    "status": result.status.value,
                    "reason": result.error_message or result.output.get("sql_gateway_reason"),
                    "sql_probe_type": self._sql_probe_type(case.user_query),
                },
            )
        return None, tuple(), {"policy_probe": "not_required"}

    def _evaluate_policy_request(
        self,
        policy_engine: PolicyEngine,
        action: str,
        probe_type: str,
    ) -> tuple[PolicyDecision, tuple[str, ...], dict[str, object]]:
        request = ToolCallRequest(
            tool_name=probe_type,
            action=action,
            asset_type="policy",
            risk_level=ToolRiskLevel.HIGH,
            requires_approval=True,
        )
        result = policy_engine.evaluate(request, self.user_context)
        return (
            result.decision,
            (probe_type, action),
            {
                "tool": probe_type,
                "action": action,
                "decision": result.decision.value,
                "reasons": tuple(reason.message for reason in result.reasons),
            },
        )

    @staticmethod
    def _decision_from_tool_status(status: ToolExecutionStatus) -> PolicyDecision:
        if status == ToolExecutionStatus.DENIED:
            return PolicyDecision.DENY
        if status == ToolExecutionStatus.ASKED:
            return PolicyDecision.ASK
        return PolicyDecision.ALLOW

    @staticmethod
    def _sql_probe_for_query(user_query: str) -> str | None:
        lowered = user_query.lower()
        if "select *" in lowered:
            return "select * from dwd_customer_detail_d limit 10"
        if "手机号" in user_query:
            return "select customer_phone from dwd_customer_detail_d limit 10"
        if "邮箱" in user_query:
            return "select customer_email from dwd_customer_detail_d limit 10"
        if "地址" in user_query:
            return "select shipping_address from dwd_customer_detail_d limit 10"
        if "api key" in lowered or "密码" in user_query:
            return "select api_key, password from dwd_customer_detail_d limit 10"
        if "毛利" in user_query:
            return "select gross_profit from dwd_trade_order_detail_d limit 10"
        if "超大结果集" in user_query:
            return "select order_id from dwd_trade_order_detail_d limit 20001"
        if "未登记表" in user_query:
            return "select order_id from unregistered_order_detail limit 10"
        return None

    @staticmethod
    def _sql_probe_type(user_query: str) -> str:
        if "超大结果集" in user_query:
            return "large_result"
        if "未登记表" in user_query:
            return "unknown_table"
        if "select *" in user_query.lower():
            return "select_star"
        return "sensitive_or_secret_column"
