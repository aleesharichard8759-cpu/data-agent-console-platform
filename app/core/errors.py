class RuntimeErrorBase(Exception):
    """Base exception for runtime-level errors."""


class PolicyDeniedError(RuntimeErrorBase):
    """Raised when a policy decision denies an operation."""


class UnsafeOperationError(RuntimeErrorBase):
    """Raised when a request violates a hard safety boundary."""

