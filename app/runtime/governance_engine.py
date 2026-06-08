from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.agents import AgentOrchestrator, AgentTaskContext, build_default_orchestrator
from app.audit import AuditLogger, InMemoryAuditLogger
from app.core.errors import RuntimeErrorBase
from app.domain.assets import DataDomain
from app.domain.audit import AuditActor, AuditEvent, AuditEventType, AuditTarget
from app.domain.common import DomainModel, new_id
from app.domain.identity import UserContext
from app.domain.tasks import (
    GovernanceTask,
    GovernanceTaskLevel,
    GovernanceTaskStatus,
    GovernanceTaskType,
)
from app.domain.tools import ToolCallRequest, ToolCallResult, ToolExecutionStatus, ToolRiskLevel
from app.hooks import HookManager, build_default_hook_manager
from app.policy import PolicyEngine
from app.runtime.plan_mode import GovernancePlan, PlanModeManager, PlanModeState
from app.tools import (
    DataToolRegistry,
    GenerateQualityRulesTool,
    GetMetricDefinitionTool,
    QuerySQLTool,
    SearchMetadataTool,
    ToolExecutionContext,
)


class GovernanceEngineError(RuntimeErrorBase):
    """Raised when the governance engine cannot continue safely."""


class GovernanceStepNode(StrEnum):
    REQUEST_INTAKE = "request_intake"
    TASK_CLASSIFICATION = "task_classification"
    CLARIFICATION = "clarification"
    ASSET_MAPPING = "asset_mapping"
    GOVERNANCE_PLANNING = "governance_planning"
    EVIDENCE_COLLECTION = "evidence_collection"
    RISK_REVIEW = "risk_review"
    RESULT_SYNTHESIS = "result_synthesis"
    KNOWLEDGE_PERSIST = "knowledge_persist"


class GovernanceStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    WAITING_APPROVAL = "waiting_approval"
    DENIED = "denied"
    FAILED = "failed"


class TaskRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    DENIED = "denied"
    FAILED = "failed"


class GovernanceStep(DomainModel):
    step_id: UUID = Field(default_factory=new_id, description="Unique step id.")
    task_id: UUID = Field(description="Governance task id.")
    node: GovernanceStepNode = Field(description="Nine-node governance workflow node.")
    status: GovernanceStepStatus = Field(
        default=GovernanceStepStatus.PENDING,
        description="Step execution status.",
    )
    tool_request: ToolCallRequest | None = Field(
        default=None,
        description="Optional DataTool request for this step.",
    )
    observation: str | None = Field(default=None, description="Safe step observation.")
    audit_refs: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Audit event ids related to this step.",
    )


class TaskRunResult(DomainModel):
    task_id: UUID = Field(description="Governance task id.")
    status: TaskRunStatus = Field(description="Task run status.")
    steps: tuple[GovernanceStep, ...] = Field(description="Executed workflow steps.")
    evidence: tuple[dict[str, object], ...] = Field(
        default_factory=tuple,
        description="Safe evidence collected by tools.",
    )
    recommendations: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Deterministic governance recommendations.",
    )
    business_result: dict[str, object] = Field(
        default_factory=dict,
        description="Business-facing result summary for console workbench rendering.",
    )
    required_approvals: tuple[dict[str, object], ...] = Field(
        default_factory=tuple,
        description="Approval placeholders created by Plan Mode or policy ASK.",
    )
    audit_refs: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Audit event ids produced during the run.",
    )


class GovernanceEngine:
    """Deterministic governance task loop. It does not call an LLM or real databases."""

    workflow_nodes: tuple[GovernanceStepNode, ...] = (
        GovernanceStepNode.REQUEST_INTAKE,
        GovernanceStepNode.TASK_CLASSIFICATION,
        GovernanceStepNode.CLARIFICATION,
        GovernanceStepNode.ASSET_MAPPING,
        GovernanceStepNode.GOVERNANCE_PLANNING,
        GovernanceStepNode.EVIDENCE_COLLECTION,
        GovernanceStepNode.RISK_REVIEW,
        GovernanceStepNode.RESULT_SYNTHESIS,
        GovernanceStepNode.KNOWLEDGE_PERSIST,
    )

    def __init__(
        self,
        *,
        policy_engine: PolicyEngine | None = None,
        tool_registry: DataToolRegistry | None = None,
        hook_manager: HookManager | None = None,
        audit_logger: AuditLogger | None = None,
        agent_orchestrator: AgentOrchestrator | None = None,
    ) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self.audit_logger = audit_logger or InMemoryAuditLogger()
        self.hook_manager = hook_manager or build_default_hook_manager()
        self.tool_registry = tool_registry or self._build_tool_registry(self.hook_manager)
        self.agent_orchestrator = agent_orchestrator or build_default_orchestrator(
            policy_engine=self.policy_engine,
            audit_logger=self.audit_logger,
        )
        self._session_id: str | None = None
        self._user_context: UserContext | None = None
        self._tasks: dict[UUID, GovernanceTask] = {}
        self._prompts: dict[UUID, str] = {}
        self._plan_managers: dict[UUID, PlanModeManager] = {}
        self._last_run: TaskRunResult | None = None

    def start_session(self, user_context: UserContext) -> str:
        self._user_context = user_context
        self._session_id = str(new_id())
        self._log_task_event(
            AuditEventType.SESSION_STARTED,
            "session.start",
            "started",
            "Governance engine session started.",
        )
        return self._session_id

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def user_context(self) -> UserContext | None:
        return self._user_context

    def create_task(self, user_prompt: str) -> GovernanceTask:
        self._require_session()
        task = self.classify_task(user_prompt)
        self._tasks[task.task_id] = task
        self._prompts[task.task_id] = user_prompt
        self._log_task_event(
            AuditEventType.TASK_CREATED,
            "task.create",
            "created",
            "Governance task created from user prompt.",
            task=task,
        )
        return task

    def classify_task(self, user_prompt: str) -> GovernanceTask:
        prompt = user_prompt.strip()
        if not prompt:
            raise GovernanceEngineError("User prompt must not be empty.")
        task_type = self._classify_task_type(prompt)
        task_level = self._classify_task_level(prompt)
        return GovernanceTask(
            title=self._title_from_prompt(prompt),
            task_type=task_type,
            task_level=task_level,
            status=GovernanceTaskStatus.CREATED,
            domain=self._classify_domain(prompt),
            objective=prompt,
            created_by=self._user_context.user_id if self._user_context else "anonymous",
            requires_approval=task_level in {GovernanceTaskLevel.G4, GovernanceTaskLevel.G5},
            allow_in_model_context=task_level
            not in {GovernanceTaskLevel.G4, GovernanceTaskLevel.G5},
        )

    def run_task(self, task_id: UUID | str) -> TaskRunResult:
        self._require_session()
        task = self._get_task(task_id)
        steps: list[GovernanceStep] = []
        evidence: list[dict[str, object]] = []
        recommendations: list[str] = []
        required_approvals: list[dict[str, object]] = []
        run_start_index = len(self.audit_logger.list_events())

        for node in self.workflow_nodes:
            step = GovernanceStep(task_id=task.task_id, node=node)
            if node == GovernanceStepNode.ASSET_MAPPING:
                step = step.model_copy(update={"tool_request": self._metadata_request(task)})
            elif node == GovernanceStepNode.EVIDENCE_COLLECTION:
                step = step.model_copy(update={"tool_request": self._evidence_request(task)})

            if node == GovernanceStepNode.GOVERNANCE_PLANNING and self._requires_plan_mode(task):
                plan = self._create_plan_mode(task)
                required_approvals.append(self._approval_summary(plan))
                updated_step = step.model_copy(
                    update={
                        "status": GovernanceStepStatus.WAITING_APPROVAL,
                        "observation": "Task requires Governance Plan Mode approval.",
                    }
                )
                steps.append(updated_step)
                return self._build_run_result(
                    task,
                    TaskRunStatus.WAITING_APPROVAL,
                    steps,
                    evidence,
                    recommendations,
                    required_approvals,
                    run_start_index,
                )

            executed_step, result = self.execute_step(step)
            steps.append(executed_step)
            if result is not None:
                if result.status == ToolExecutionStatus.DENIED:
                    return self._build_run_result(
                        task,
                        TaskRunStatus.DENIED,
                        steps,
                        evidence,
                        recommendations,
                        required_approvals,
                        run_start_index,
                    )
                if result.status == ToolExecutionStatus.ASKED:
                    required_approvals.append(
                        {
                            "tool_call_id": str(result.tool_call_id),
                            "reason": result.error_message or "Approval required.",
                        }
                    )
                if result.status == ToolExecutionStatus.SUCCEEDED:
                    evidence.append(self._safe_evidence(executed_step.node, result))

            if node == GovernanceStepNode.RESULT_SYNTHESIS:
                subagent_result = self._run_subagents(task)
                evidence.append(
                    {
                        "node": "subagents",
                        "agents": tuple(
                            result.agent_name for result in subagent_result.agent_results
                        ),
                        "status": subagent_result.status,
                        "vetoed_by": subagent_result.vetoed_by,
                    }
                )
                recommendations.extend(self._recommendations_for(task))
                recommendations.extend(subagent_result.summary.get("recommendations", ()))
                if subagent_result.status == "vetoed":
                    required_approvals.append(
                        {
                            "reason": "SecurityAgent vetoed model-context eligibility.",
                            "vetoed_by": subagent_result.vetoed_by,
                        }
                    )

        self.complete_task(task.task_id)
        return self._build_run_result(
            task,
            TaskRunStatus.COMPLETED,
            steps,
            evidence,
            recommendations,
            required_approvals,
            run_start_index,
        )

    def execute_step(self, step: GovernanceStep) -> tuple[GovernanceStep, ToolCallResult | None]:
        task = self._get_task(step.task_id)
        if step.tool_request is None:
            return (
                step.model_copy(
                    update={
                        "status": GovernanceStepStatus.SUCCEEDED,
                        "observation": self._observation_for(step.node, task),
                    }
                ),
                None,
            )

        tool = self.tool_registry.get_tool(step.tool_request.tool_name)
        plan_manager = self._plan_managers.get(task.task_id)
        if plan_manager is not None:
            plan_manager.assert_tool_allowed(tool)

        result = self.tool_registry.execute_tool(
            step.tool_request,
            ToolExecutionContext(
                user_context=self._require_session(),
                task_context=task,
                policy_engine=self.policy_engine,
                audit_logger=self.audit_logger,
                dry_run=True,
                plan_mode=plan_manager is not None
                and plan_manager.state
                in {
                    PlanModeState.PLANNING,
                    PlanModeState.WAITING_APPROVAL,
                    PlanModeState.APPROVED,
                    PlanModeState.EXECUTING,
                },
                session_id=self._session_id,
                agent_name="governance_engine",
            ),
        )
        return (
            step.model_copy(
                update={
                    "status": self._step_status_from_tool_result(result),
                    "observation": self._tool_observation(result),
                    "audit_refs": self._audit_refs_from_result(result),
                }
            ),
            result,
        )

    def complete_task(self, task_id: UUID | str) -> GovernanceTask:
        task = self._get_task(task_id)
        completed = task.model_copy(update={"status": GovernanceTaskStatus.COMPLETED})
        self._tasks[task.task_id] = completed
        self._log_task_event(
            AuditEventType.TASK_COMPLETED,
            "task.complete",
            "completed",
            "Governance task completed.",
            task=completed,
        )
        return completed

    def run_subagents(self, task_id: UUID | str):
        task = self._get_task(task_id)
        return self._run_subagents(task)

    def get_task(self, task_id: UUID | str) -> GovernanceTask | None:
        try:
            return self._tasks.get(UUID(str(task_id)))
        except ValueError:
            return None

    def get_plan(self, plan_id: UUID | str) -> tuple[GovernancePlan, PlanModeState] | None:
        manager = self._find_plan_manager(plan_id)
        if manager is None:
            return None
        plan = manager.get_plan(plan_id)
        if plan is None:
            return None
        return plan, manager.state

    def approve_plan(
        self,
        plan_id: UUID | str,
        approver: str,
    ) -> tuple[GovernancePlan, PlanModeState]:
        manager = self._require_plan_manager(plan_id)
        plan = manager.approve_plan(plan_id, approver)
        return plan, manager.state

    def reject_plan(
        self, plan_id: UUID | str, approver: str, reason: str
    ) -> tuple[GovernancePlan, PlanModeState]:
        manager = self._require_plan_manager(plan_id)
        plan = manager.reject_plan(plan_id, approver, reason)
        return plan, manager.state

    @staticmethod
    def _build_tool_registry(hook_manager: HookManager) -> DataToolRegistry:
        registry = DataToolRegistry(hook_manager=hook_manager)
        registry.register(SearchMetadataTool())
        registry.register(GetMetricDefinitionTool())
        registry.register(GenerateQualityRulesTool())
        registry.register(QuerySQLTool())
        return registry

    def _create_plan_mode(self, task: GovernanceTask) -> GovernancePlan:
        manager = PlanModeManager(
            audit_logger=self.audit_logger,
            user_context=self._require_session(),
            session_id=self._session_id,
            agent_name="governance_engine",
        )
        manager.enter_plan_mode(task)
        plan = manager.create_plan(
            title=f"{task.title} - Governance Plan",
            summary="Plan mode required before high-risk governance execution.",
            affected_assets=(self._asset_hint(task),),
            proposed_actions=(self._proposed_action(task),),
            risk_level=task.task_level,
            required_approvers=("mock_security_reviewer",),
            rollback_plan="Keep the current mock governance state and discard proposed changes.",
            approval_required=True,
            allowed_tools_after_approval=("search_metadata", "get_metric_definition"),
        )
        manager.request_approval(plan)
        self._plan_managers[task.task_id] = manager
        return plan

    def _run_subagents(self, task: GovernanceTask):
        return self.agent_orchestrator.run(
            task,
            AgentTaskContext(
                task=task,
                user_context=self._require_session(),
                session_id=self._session_id,
                dry_run=True,
            ),
        )

    def _build_run_result(
        self,
        task: GovernanceTask,
        status: TaskRunStatus,
        steps: list[GovernanceStep],
        evidence: list[dict[str, object]],
        recommendations: list[str],
        required_approvals: list[dict[str, object]],
        run_start_index: int,
    ) -> TaskRunResult:
        audit_refs = tuple(
            str(event.event_id) for event in self.audit_logger.list_events()[run_start_index:]
        )
        result = TaskRunResult(
            task_id=task.task_id,
            status=status,
            steps=tuple(steps),
            evidence=tuple(evidence),
            recommendations=tuple(recommendations),
            business_result=self._business_result_for(
                task,
                status,
                evidence,
                recommendations,
                required_approvals,
            ),
            required_approvals=tuple(required_approvals),
            audit_refs=audit_refs,
        )
        self._last_run = result
        return result

    def _metadata_request(self, task: GovernanceTask) -> ToolCallRequest:
        return ToolCallRequest(
            tool_name="search_metadata",
            action="metadata.query",
            asset_type="metadata",
            parameters={"query": self._query_hint(task), "limit": 5},
            risk_level=ToolRiskLevel.LOW,
        )

    def _evidence_request(self, task: GovernanceTask) -> ToolCallRequest:
        if task.task_type == GovernanceTaskType.METRIC_GOVERNANCE:
            return ToolCallRequest(
                tool_name="get_metric_definition",
                action="metric.definition.query",
                asset_type="metric_definition",
                parameters={"metric_name": "order_count"},
                risk_level=ToolRiskLevel.LOW,
            )
        return self._metadata_request(task)

    @staticmethod
    def _classify_task_type(prompt: str) -> GovernanceTaskType:
        if "质量规则" in prompt:
            return GovernanceTaskType.DATA_QUALITY
        if "字段注释" in prompt or "字段解释" in prompt or "数据字典" in prompt:
            return GovernanceTaskType.METADATA_COMPLETION
        if "指标" in prompt or "口径" in prompt:
            return GovernanceTaskType.METRIC_GOVERNANCE
        if "权限" in prompt or "开放" in prompt or "毛利" in prompt:
            return GovernanceTaskType.PERMISSION_INSPECTION
        lowered = prompt.lower()
        if (
            "敏感" in prompt
            or "脱敏" in prompt
            or "手机号" in prompt
            or "邮箱" in prompt
            or "地址" in prompt
            or "密码" in prompt
            or "审计" in prompt
            or "select *" in lowered
            or "api key" in lowered
            or "token" in lowered
            or "secret" in lowered
        ):
            return GovernanceTaskType.SENSITIVE_DATA_DISCOVERY
        if "血缘" in prompt or "影响" in prompt:
            return GovernanceTaskType.LINEAGE_IMPACT
        if "治理报告" in prompt:
            return GovernanceTaskType.GOVERNANCE_REPORT
        if ("治理" in prompt and "域" in prompt) or "chatbi" in prompt.lower():
            return GovernanceTaskType.DATA_DOMAIN_GOVERNANCE
        return GovernanceTaskType.ASSET_INVENTORY

    @staticmethod
    def _classify_task_level(prompt: str) -> GovernanceTaskLevel:
        lowered = prompt.lower()
        if (
            any(keyword in prompt for keyword in ("删除", "关闭审计", "生产变更", "绕过脱敏"))
            or "api key" in lowered
            or "token" in lowered
            or "secret" in lowered
            or "绕过 dlp" in lowered
            or "密码" in prompt
        ):
            return GovernanceTaskLevel.G5
        if any(
            keyword in prompt
            for keyword in (
                "敏感",
                "脱敏",
                "权限",
                "审批",
                "ChatBI",
                "手机号",
                "邮箱",
                "地址",
                "毛利",
                "超大结果集",
                "未登记表",
            )
        ) or "select *" in lowered or "chatbi" in lowered:
            return GovernanceTaskLevel.G4
        if any(keyword in prompt for keyword in ("血缘", "影响", "口径")):
            return GovernanceTaskLevel.G3
        return GovernanceTaskLevel.G2

    @staticmethod
    def _classify_domain(prompt: str) -> DataDomain:
        if "订单" in prompt or "交易" in prompt:
            return DataDomain.TRADE
        if "商品" in prompt or "SKU" in prompt.upper():
            return DataDomain.PRODUCT
        if "库存" in prompt:
            return DataDomain.INVENTORY
        if "财务" in prompt:
            return DataDomain.FINANCE
        if "权限" in prompt or "安全" in prompt:
            return DataDomain.SECURITY
        return DataDomain.UNKNOWN

    @staticmethod
    def _title_from_prompt(prompt: str) -> str:
        title = prompt.strip().replace("\n", " ")
        return title[:80] or "Governance task"

    @staticmethod
    def _requires_plan_mode(task: GovernanceTask) -> bool:
        return task.task_level in {GovernanceTaskLevel.G4, GovernanceTaskLevel.G5}

    @staticmethod
    def _query_hint(task: GovernanceTask) -> str:
        prompt = task.objective.lower()
        if "rma" in prompt or "售后" in task.objective or "退货" in task.objective or "客诉" in task.objective:
            return "rma"
        if task.domain == DataDomain.TRADE:
            return "order"
        if task.domain == DataDomain.PRODUCT:
            return "product"
        return "governance"

    @staticmethod
    def _asset_hint(task: GovernanceTask) -> str:
        prompt = task.objective.lower()
        if "rma" in prompt or "售后" in task.objective or "退货" in task.objective or "客诉" in task.objective:
            return "dwd_after_sale_rma_detail_d"
        if task.domain == DataDomain.TRADE:
            return "dwd_trade_order_detail_d"
        if task.domain == DataDomain.PRODUCT:
            return "dim_product_sku"
        return "governed_mock_asset"

    @staticmethod
    def _proposed_action(task: GovernanceTask) -> str:
        if task.task_type == GovernanceTaskType.PERMISSION_INSPECTION:
            return "permission.inspect"
        if task.task_type == GovernanceTaskType.SENSITIVE_DATA_DISCOVERY:
            return "sensitive_data.review"
        return "governance.review"

    @staticmethod
    def _recommendations_for(task: GovernanceTask) -> tuple[str, ...]:
        if task.task_type == GovernanceTaskType.DATA_QUALITY:
            return (
                "Review not-null, uniqueness, freshness, and value-range rules for mapped assets.",
                "Submit actual quality-rule creation through Plan Mode if changes are required.",
            )
        if task.task_type == GovernanceTaskType.METADATA_COMPLETION:
            return (
                "Complete field comments, owner, domain, and sensitivity tags in metadata catalog.",
            )
        if task.task_type == GovernanceTaskType.METRIC_GOVERNANCE:
            return ("Confirm metric definition, aggregation, grain, and source assets.",)
        return ("Review collected evidence and route high-risk changes through approval.",)

    @staticmethod
    def _business_result_for(
        task: GovernanceTask,
        status: TaskRunStatus,
        evidence: list[dict[str, object]],
        recommendations: list[str],
        required_approvals: list[dict[str, object]],
    ) -> dict[str, object]:
        base = {
            "title": task.title,
            "task_type": task.task_type.value,
            "task_level": task.task_level.value,
            "status": status.value,
            "summary": "",
            "metrics": [],
            "sections": [],
            "next_actions": list(recommendations) or ["Review collected evidence and keep audit references."],
            "approval_required": bool(required_approvals),
        }

        rma_assets = [
            {
                "name": "dwd_after_sale_rma_detail_d",
                "layer": "DWD",
                "domain": "RMA 售后",
                "owner": "缺失",
                "sensitivity": "L2",
                "fields": 5,
                "issues": "缺 owner、rma_reason 字段注释缺失",
                "action": "补齐 owner 和字段说明后纳入语义层",
            },
            {
                "name": "ads_rma_metric_1d",
                "layer": "ADS",
                "domain": "RMA 售后",
                "owner": "analytics_owner",
                "sensitivity": "L2",
                "fields": 8,
                "issues": "指标口径需绑定 complaint_rate 定义",
                "action": "绑定 RMA 问数助手指标口径",
            },
            {
                "name": "dwd_customer_detail_d",
                "layer": "DWD",
                "domain": "客户",
                "owner": "customer_data_owner",
                "sensitivity": "L3",
                "fields": 4,
                "issues": "包含手机号、邮箱、地址",
                "action": "保持脱敏输出，禁止明细导出",
            },
        ]

        if task.task_type == GovernanceTaskType.ASSET_INVENTORY:
            return {
                **base,
                "summary": "已识别 RMA 售后域 3 个核心数据资产，其中 1 个 owner 缺失、1 个包含 L3 客户敏感字段。",
                "metrics": [
                    {"label": "核心资产", "value": 3},
                    {"label": "缺 Owner", "value": 1},
                    {"label": "高敏资产", "value": 1},
                    {"label": "建议动作", "value": 3},
                ],
                "sections": [
                    {
                        "type": "asset_table",
                        "title": "核心数据资产",
                        "columns": ["资产名", "层级", "数据域", "负责人", "敏感等级", "字段数", "治理问题", "建议动作"],
                        "rows": rma_assets,
                    }
                ],
                "next_actions": [
                    "为 dwd_after_sale_rma_detail_d 指定 RMA 数据 Owner。",
                    "补齐 rma_reason 字段注释和业务枚举说明。",
                    "将 ads_rma_metric_1d 绑定到 RMA 问数助手语义层。",
                ],
                "approval_required": False,
            }

        if task.task_type == GovernanceTaskType.SENSITIVE_DATA_DISCOVERY:
            return {
                **base,
                "summary": "已识别 RMA 链路中 3 个敏感字段，客户联系方式不得进入模型上下文或明细导出。",
                "metrics": [
                    {"label": "敏感字段", "value": 3},
                    {"label": "L3 字段", "value": 3},
                    {"label": "需脱敏规则", "value": 3},
                    {"label": "审批状态", "value": "待审批" if required_approvals else "无需审批"},
                ],
                "sections": [
                    {
                        "type": "sensitive_field_table",
                        "title": "敏感字段识别结果",
                        "columns": ["字段", "所在表", "敏感等级", "风险", "建议规则"],
                        "rows": [
                            {"field": "customer_phone", "table": "dwd_customer_detail_d", "level": "L3", "risk": "手机号明细", "rule": "hash + 仅聚合展示"},
                            {"field": "customer_email", "table": "dwd_customer_detail_d", "level": "L3", "risk": "邮箱明细", "rule": "redact + 禁止导出"},
                            {"field": "shipping_address", "table": "dwd_customer_detail_d", "level": "L3", "risk": "地址明细", "rule": "区域泛化 + 审批访问"},
                        ],
                    }
                ],
                "next_actions": [
                    "提交 DLP / Masking 规则变更审批。",
                    "问数助手仅允许接收脱敏摘要，不允许接收客户明文明细。",
                    "将本次结果加入安全回归 Case。",
                ],
            }

        if task.task_type == GovernanceTaskType.DATA_QUALITY:
            return {
                **base,
                "summary": "已为 RMA 指标链路生成 4 条质量规则建议，覆盖完整性、及时性、枚举值和数值范围。",
                "metrics": [
                    {"label": "规则建议", "value": 4},
                    {"label": "高优先级", "value": 2},
                    {"label": "影响表", "value": 2},
                    {"label": "需审批", "value": "否"},
                ],
                "sections": [
                    {
                        "type": "quality_rule_table",
                        "title": "质量规则建议",
                        "columns": ["规则", "对象", "优先级", "失败影响", "建议处理"],
                        "rows": [
                            {"rule": "metric_date 不为空", "target": "ads_rma_metric_1d.metric_date", "priority": "高", "impact": "问数时间口径失效", "action": "上线前阻断"},
                            {"rule": "complaint_rate 在 0-1 之间", "target": "ads_rma_metric_1d.complaint_rate", "priority": "高", "impact": "客诉率异常", "action": "告警并回滚"},
                            {"rule": "rma_reason 不为空", "target": "dwd_after_sale_rma_detail_d.rma_reason", "priority": "中", "impact": "归因分析缺失", "action": "补充枚举映射"},
                            {"rule": "T+1 分区新鲜度", "target": "ads_rma_metric_1d", "priority": "中", "impact": "管理层日报延迟", "action": "生成调度告警"},
                        ],
                    }
                ],
                "next_actions": [
                    "将高优先级规则加入发布前检查。",
                    "把 complaint_rate 范围校验接入 Eval Case。",
                    "为 rma_reason 补充标准枚举。",
                ],
                "approval_required": False,
            }

        if task.task_type == GovernanceTaskType.METADATA_COMPLETION:
            return {
                **base,
                "summary": "已发现 RMA 明细表字段说明不完整，建议优先补齐原因、责任人和业务枚举。",
                "metrics": [
                    {"label": "待补字段", "value": 1},
                    {"label": "缺 Owner 表", "value": 1},
                    {"label": "影响任务", "value": "异常诊断"},
                ],
                "sections": [
                    {
                        "type": "metadata_table",
                        "title": "元数据补全清单",
                        "columns": ["对象", "缺失项", "影响", "建议"],
                        "rows": [
                            {"object": "dwd_after_sale_rma_detail_d.rma_reason", "missing": "字段注释 / 枚举解释", "impact": "问数回答无法解释客诉原因", "action": "补充 RMA 原因字典"},
                            {"object": "dwd_after_sale_rma_detail_d", "missing": "Owner", "impact": "审批和质量责任不明确", "action": "指定售后数据负责人"},
                        ],
                    }
                ],
                "next_actions": ["补齐字段注释后重新运行元数据 Eval。"],
                "approval_required": False,
            }

        if task.task_type == GovernanceTaskType.METRIC_GOVERNANCE:
            return {
                **base,
                "summary": "已生成 RMA 客诉率指标口径治理卡，建议确认分子、分母、时间粒度和过滤条件。",
                "metrics": [
                    {"label": "指标", "value": 1},
                    {"label": "待确认项", "value": 3},
                    {"label": "风险等级", "value": task.task_level.value},
                ],
                "sections": [
                    {
                        "type": "metric_card",
                        "title": "指标口径卡",
                        "rows": [
                            {"label": "标准指标", "value": "RMA 客诉率"},
                            {"label": "计算口径", "value": "质量问题客诉单量 / RMA 总单量"},
                            {"label": "时间粒度", "value": "按 metric_date 日粒度聚合，月度按分子分母汇总后重算"},
                            {"label": "待确认", "value": "是否排除取消单、重复客诉、非质量原因 RMA"},
                        ],
                    }
                ],
                "next_actions": ["由数据产品经理确认指标口径后发布到语义层。"],
                "approval_required": False,
            }

        if task.task_type == GovernanceTaskType.PERMISSION_INSPECTION:
            return {
                **base,
                "summary": "已发现客户域和财务毛利字段属于高风险访问对象，需要审批后才能变更权限。",
                "metrics": [
                    {"label": "风险权限", "value": 2},
                    {"label": "需审批", "value": "是"},
                    {"label": "建议拒绝", "value": 1},
                ],
                "sections": [
                    {
                        "type": "permission_table",
                        "title": "权限巡检结果",
                        "columns": ["对象", "风险", "当前裁决", "建议"],
                        "rows": [
                            {"object": "dwd_customer_detail_d.customer_phone", "risk": "客户手机号明细", "decision": "拒绝", "action": "仅开放聚合统计"},
                            {"object": "dwd_trade_order_detail_d.gross_profit", "risk": "财务毛利字段", "decision": "需审批", "action": "限定财务角色访问"},
                        ],
                    }
                ],
                "next_actions": ["提交权限策略审批，并生成回滚版本。"],
            }

        if task.task_type == GovernanceTaskType.LINEAGE_IMPACT:
            return {
                **base,
                "summary": "已识别 RMA 明细表下游影响 1 个管理看板和 1 条问数指标链路。",
                "metrics": [
                    {"label": "上游表", "value": 1},
                    {"label": "下游对象", "value": 2},
                    {"label": "影响等级", "value": task.task_level.value},
                ],
                "sections": [
                    {
                        "type": "lineage_table",
                        "title": "血缘影响",
                        "columns": ["上游资产", "下游对象", "影响", "建议"],
                        "rows": [
                            {"source": "dwd_after_sale_rma_detail_d", "target": "ads_rma_metric_1d", "impact": "RMA 客诉率计算", "action": "变更前运行指标回归"},
                            {"source": "ads_rma_metric_1d", "target": "RMA 问数助手", "impact": "管理者摘要回答", "action": "同步更新 Case / Eval"},
                        ],
                    }
                ],
                "next_actions": ["在发布中心执行环境差异对比和回归 Eval。"],
                "approval_required": False,
            }

        if task.task_type == GovernanceTaskType.DATA_DOMAIN_GOVERNANCE:
            return {
                **base,
                "summary": "已生成 RMA 域治理建议，重点是数据域归属、语义层绑定、安全策略和 Eval 闭环。",
                "metrics": [
                    {"label": "治理对象", "value": 4},
                    {"label": "缺口", "value": 3},
                    {"label": "需审批", "value": "是" if required_approvals else "否"},
                ],
                "sections": [
                    {
                        "type": "domain_gap_table",
                        "title": "数据域治理缺口",
                        "columns": ["治理对象", "当前问题", "建议动作"],
                        "rows": [
                            {"object": "RMA 售后域", "issue": "域 owner 未明确", "action": "指定业务 Owner 和数据 Steward"},
                            {"object": "RMA 问数助手", "issue": "语义层与 Runtime 策略未联动", "action": "绑定指标、权限和 DLP 策略"},
                            {"object": "Case / Eval", "issue": "缺少拒答和审批 Case", "action": "补充安全红队数据集"},
                        ],
                    }
                ],
                "next_actions": ["将缺口拆成治理任务并进入发布前检查。"],
            }

        if task.task_type == GovernanceTaskType.GOVERNANCE_REPORT:
            return {
                **base,
                "summary": "已生成 RMA 治理报告摘要：资产可用性基本达标，安全与口径治理仍有 3 个待办。",
                "metrics": [
                    {"label": "资产健康度", "value": "78%"},
                    {"label": "安全风险", "value": 2},
                    {"label": "口径待确认", "value": 1},
                    {"label": "发布建议", "value": "谨慎上线"},
                ],
                "sections": [
                    {
                        "type": "report_summary",
                        "title": "治理报告摘要",
                        "rows": [
                            {"label": "总体结论", "value": "RMA 问数可以进入灰度，但敏感字段和指标口径需先完成审批与确认。"},
                            {"label": "上线阻断", "value": "客户手机号、邮箱、地址不得明文进入模型上下文。"},
                            {"label": "建议节奏", "value": "先开放管理者摘要版，再开放数据团队过程版。"},
                        ],
                    }
                ],
                "next_actions": ["进入发布中心执行 Runtime / Product 双版本检查。"],
                "approval_required": False,
            }

        return {
            **base,
            "summary": "治理任务已完成，Runtime 已记录执行节点、审计引用和建议动作。",
            "metrics": [
                {"label": "执行节点", "value": len(evidence)},
                {"label": "审计状态", "value": "已记录"},
            ],
        }

    @staticmethod
    def _approval_summary(plan: GovernancePlan) -> dict[str, object]:
        return {
            "plan_id": str(plan.plan_id),
            "task_id": str(plan.task_id),
            "risk_level": plan.risk_level.value,
            "required_approvers": plan.required_approvers,
            "allowed_tools_after_approval": plan.allowed_tools_after_approval,
        }

    @staticmethod
    def _safe_evidence(node: GovernanceStepNode, result: ToolCallResult) -> dict[str, object]:
        data = result.output.get("data")
        if isinstance(data, dict):
            return {
                "node": node.value,
                "keys": tuple(sorted(data.keys())),
                "summary": f"tool_result_status={result.status.value}",
            }
        return {"node": node.value, "summary": f"tool_result_status={result.status.value}"}

    @staticmethod
    def _step_status_from_tool_result(result: ToolCallResult) -> GovernanceStepStatus:
        if result.status == ToolExecutionStatus.DENIED:
            return GovernanceStepStatus.DENIED
        if result.status == ToolExecutionStatus.ASKED:
            return GovernanceStepStatus.WAITING_APPROVAL
        if result.status == ToolExecutionStatus.FAILED:
            return GovernanceStepStatus.FAILED
        return GovernanceStepStatus.SUCCEEDED

    @staticmethod
    def _tool_observation(result: ToolCallResult) -> str:
        if result.status == ToolExecutionStatus.DENIED:
            return result.error_message or "Tool request denied."
        if result.status == ToolExecutionStatus.ASKED:
            return result.error_message or "Tool request requires approval."
        return f"Tool request finished with status {result.status.value}."

    @staticmethod
    def _audit_refs_from_result(result: ToolCallResult) -> tuple[str, ...]:
        audit_event_id = result.output.get("audit_event_id")
        if isinstance(audit_event_id, str):
            return (audit_event_id,)
        return tuple()

    @staticmethod
    def _observation_for(node: GovernanceStepNode, task: GovernanceTask) -> str:
        return f"{node.value} completed for {task.task_type.value}."

    def _get_task(self, task_id: UUID | str) -> GovernanceTask:
        try:
            task_uuid = UUID(str(task_id))
        except ValueError as exc:
            raise GovernanceEngineError(f"Invalid task id: {task_id}") from exc
        try:
            return self._tasks[task_uuid]
        except KeyError as exc:
            raise GovernanceEngineError(f"Governance task not found: {task_id}") from exc

    def _find_plan_manager(self, plan_id: UUID | str) -> PlanModeManager | None:
        try:
            plan_uuid = UUID(str(plan_id))
        except ValueError:
            return None
        for manager in self._plan_managers.values():
            if manager.get_plan(plan_uuid) is not None:
                return manager
        return None

    def _require_plan_manager(self, plan_id: UUID | str) -> PlanModeManager:
        manager = self._find_plan_manager(plan_id)
        if manager is None:
            raise GovernanceEngineError(f"Governance plan not found: {plan_id}")
        return manager

    def _require_session(self) -> UserContext:
        if self._user_context is None or self._session_id is None:
            raise GovernanceEngineError("GovernanceEngine session has not started.")
        return self._user_context

    def _log_task_event(
        self,
        event_type: AuditEventType,
        action: str,
        outcome: str,
        reason: str,
        task: GovernanceTask | None = None,
    ) -> AuditEvent:
        user = self._user_context
        if user is None:
            raise GovernanceEngineError("Cannot audit without user context.")
        event = AuditEvent(
            event_type=event_type,
            actor=AuditActor(
                actor_id=user.user_id,
                actor_type="service" if user.is_service_account else "user",
                display_name=user.display_name,
                department=user.department.name if user.department else None,
            ),
            target=AuditTarget(
                target_id=str(task.task_id) if task is not None else self._session_id or "session",
                target_type="governance_task" if task is not None else "session",
                qualified_name=task.title if task is not None else "governance_engine_session",
            ),
            user_id=user.user_id,
            role=user.roles[0].value if user.roles else None,
            session_id=self._session_id,
            task_id=str(task.task_id) if task is not None else None,
            agent_name="governance_engine",
            action=action,
            outcome=outcome,
            reason=reason,
            request_summary=task.objective if task is not None else "session",
            result_summary=f"outcome={outcome}",
            raw_payload_allowed=False,
        )
        return self.audit_logger.log_event(event)
