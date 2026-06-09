from __future__ import annotations

import argparse
import json
from typing import Any

from app.audit import InMemoryAuditLogger
from app.domain.common import new_id
from app.domain.identity import UserContext, UserRole
from app.evals import EvalRunner, default_eval_cases
from app.runtime import GovernanceEngine
from app.security import SQLGateway


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "task":
        payload = _run_task(args.prompt)
    elif args.command == "sql-review":
        payload = _review_sql(args.sql)
    elif args.command == "eval" and args.eval_command == "run":
        payload = _run_evals()
    elif args.command == "audit":
        payload = _list_audit(args.task_id)
    else:
        parser.print_help()
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datagent",
        description="Data Governance Agent Runtime CLI.",
    )
    subparsers = parser.add_subparsers(dest="command")

    task_parser = subparsers.add_parser("task", help="Create and run a governance task.")
    task_parser.add_argument("prompt", help="Governance task prompt.")

    sql_parser = subparsers.add_parser("sql-review", help="Review SQL without execution.")
    sql_parser.add_argument("sql", help="SQL to review.")

    eval_parser = subparsers.add_parser("eval", help="Run evaluation suites.")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command")
    eval_subparsers.add_parser("run", help="Run the default evaluation suite.")

    audit_parser = subparsers.add_parser("audit", help="List in-memory audit events.")
    audit_parser.add_argument("--task-id", default=None, help="Optional task id filter.")
    return parser


def _run_task(prompt: str) -> dict[str, Any]:
    audit_logger = InMemoryAuditLogger()
    engine = GovernanceEngine(audit_logger=audit_logger)
    session_id = engine.start_session(_demo_user())
    task = engine.create_task(prompt)
    result = engine.run_task(task.task_id)
    return {
        "trace_id": _trace_id(),
        "audit_refs": result.audit_refs,
        "session_id": session_id,
        "task_id": str(task.task_id),
        "status": result.status.value,
        "task_type": task.task_type.value,
        "task_level": task.task_level.value,
        "required_approvals": result.required_approvals,
        "recommendations": result.recommendations,
    }


def _review_sql(sql: str) -> dict[str, Any]:
    audit_logger = InMemoryAuditLogger()
    review = SQLGateway().review_sql(
        sql,
        _demo_user(),
        audit_logger=audit_logger,
        agent_name="cli",
        tool_name="sql_review",
    )
    events = audit_logger.list_events()
    return {
        "trace_id": _trace_id(),
        "audit_refs": tuple(str(event.event_id) for event in events),
        "allowed": review.allowed,
        "decision": review.decision.value,
        "risks": tuple(risk.model_dump(mode="json") for risk in review.risks),
        "rewritten_sql": review.rewritten_sql,
        "reason": review.reason,
        "required_approval": review.required_approval,
    }


def _run_evals() -> dict[str, Any]:
    runner = EvalRunner()
    results = runner.run_suite(default_eval_cases())
    report = runner.produce_report(results)
    return {
        "trace_id": _trace_id(),
        "audit_refs": tuple(),
        "total_cases": report.total_cases,
        "passed_cases": report.passed_cases,
        "failed_cases": report.failed_cases,
        "pass_rate": report.pass_rate,
    }


def _list_audit(task_id: str | None) -> dict[str, Any]:
    del task_id
    return {
        "trace_id": _trace_id(),
        "audit_refs": tuple(),
        "events": tuple(),
        "note": (
            "CLI audit uses process-local memory; "
            "API audit should be used for live tasks."
        ),
    }


def _demo_user() -> UserContext:
    return UserContext(
        user_id="cli_user",
        display_name="CLI Data Steward",
        roles=(UserRole.DATA_STEWARD,),
    )


def _trace_id() -> str:
    return str(new_id())


if __name__ == "__main__":
    raise SystemExit(main())
