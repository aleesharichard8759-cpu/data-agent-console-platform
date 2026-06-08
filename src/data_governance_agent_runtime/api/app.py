from __future__ import annotations

from fastapi import FastAPI

from data_governance_agent_runtime.core.models import Actor, GovernanceTask, RuntimeContext
from data_governance_agent_runtime.runtime.engine import GovernanceAgentRuntime


def create_app() -> FastAPI:
    app = FastAPI(title="Data Governance Agent Runtime", version="0.1.0")
    runtime = GovernanceAgentRuntime()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/tasks/run")
    def run_task(task: GovernanceTask) -> dict[str, object]:
        context = RuntimeContext(
            actor=Actor(actor_id="runtime_user", roles=("data_steward",)),
            purpose="governance_task",
        )
        return runtime.run(task, context).model_dump(mode="json")

    return app

