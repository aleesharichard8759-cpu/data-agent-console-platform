from enum import StrEnum


class ActionRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Decision(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class Environment(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AuditOutcome(StrEnum):
    ALLOWED = "allowed"
    ASKED = "asked"
    DENIED = "denied"
    FAILED = "failed"
    MASKED = "masked"


class SqlStatementType(StrEnum):
    SELECT = "select"
    UNKNOWN = "unknown"
    MUTATION = "mutation"
    DDL = "ddl"
