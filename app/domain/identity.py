from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from app.domain.common import DomainModel, new_id, utc_now


class UserRole(StrEnum):
    DATA_STEWARD = "data_steward"
    DATA_OWNER = "data_owner"
    DATA_ENGINEER = "data_engineer"
    DATA_ANALYST = "data_analyst"
    SECURITY_REVIEWER = "security_reviewer"
    GOVERNANCE_ADMIN = "governance_admin"
    AGENT_SERVICE = "agent_service"
    READONLY_AUDITOR = "readonly_auditor"


class Department(DomainModel):
    department_id: str = Field(description="Department identifier from the enterprise directory.")
    name: str = Field(description="Department display name.")
    parent_department_id: str | None = Field(
        default=None,
        description="Parent department identifier if this department is nested.",
    )


class UserContext(DomainModel):
    user_id: str = Field(description="Stable user identifier from IAM or SSO.")
    display_name: str = Field(description="User display name.")
    roles: tuple[UserRole, ...] = Field(default_factory=tuple, description="Assigned user roles.")
    department: Department | None = Field(default=None, description="User department context.")
    is_service_account: bool = Field(
        default=False,
        description="Whether this identity is a service account.",
    )
    allow_in_model_context: bool = Field(
        default=False,
        description="Whether this identity context may be included in model prompts.",
    )

    @field_validator("user_id", "display_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Identity fields must not be empty.")
        return value.strip()


class AuthContext(DomainModel):
    auth_context_id: UUID = Field(default_factory=new_id, description="Unique auth context id.")
    user: UserContext = Field(description="Authenticated user context.")
    session_id: str = Field(description="Runtime session identifier.")
    auth_method: str = Field(description="Authentication method, such as sso or service_token.")
    scopes: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Granted authorization scopes.",
    )
    issued_at: datetime = Field(
        default_factory=utc_now,
        description="Authentication issue timestamp.",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Authentication expiry timestamp.",
    )
    requires_approval: bool = Field(
        default=False,
        description="Whether this authenticated session requires additional approval.",
    )
