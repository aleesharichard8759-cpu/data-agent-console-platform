from __future__ import annotations

import json
import os
import re

from pydantic import Field, SecretStr

from app.core.errors import RuntimeErrorBase
from app.domain.common import DomainModel


class SecretResolutionError(RuntimeErrorBase):
    """Raised when a secret_ref cannot be resolved safely."""


class StarRocksCredentials(DomainModel):
    host: str = Field(description="StarRocks FE MySQL protocol host.")
    port: int = Field(default=9030, ge=1, le=65535, description="StarRocks FE query port.")
    user: str = Field(description="Read-only StarRocks username.")
    password: SecretStr = Field(description="Read-only StarRocks password.")
    database: str | None = Field(default=None, description="Default database.")
    connect_timeout: int = Field(default=5, ge=1, le=60, description="Connect timeout seconds.")
    read_timeout: int = Field(default=30, ge=1, le=300, description="Read timeout seconds.")


class EnvSecretProvider:
    """Resolve secret_ref values from environment variables without exposing plaintext."""

    def resolve_starrocks(self, secret_ref: str) -> StarRocksCredentials:
        payload = self._read_secret_payload(secret_ref)
        if payload is not None:
            return StarRocksCredentials.model_validate(payload)

        fallback = {
            "host": os.getenv("DATAGENT_STARROCKS_HOST"),
            "port": os.getenv("DATAGENT_STARROCKS_PORT", "9030"),
            "user": os.getenv("DATAGENT_STARROCKS_USER"),
            "password": os.getenv("DATAGENT_STARROCKS_PASSWORD"),
            "database": os.getenv("DATAGENT_STARROCKS_DATABASE"),
            "connect_timeout": os.getenv("DATAGENT_STARROCKS_CONNECT_TIMEOUT", "5"),
            "read_timeout": os.getenv("DATAGENT_STARROCKS_READ_TIMEOUT", "30"),
        }
        if fallback["host"] and fallback["user"] and fallback["password"]:
            return StarRocksCredentials.model_validate(fallback)

        env_name = self.env_name_for_ref(secret_ref)
        raise SecretResolutionError(
            "StarRocks secret_ref is not configured. Set "
            f"{env_name} to a JSON credential payload, or set DATAGENT_STARROCKS_HOST, "
            "DATAGENT_STARROCKS_USER and DATAGENT_STARROCKS_PASSWORD."
        )

    def _read_secret_payload(self, secret_ref: str) -> dict[str, object] | None:
        raw = os.getenv(self.env_name_for_ref(secret_ref))
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SecretResolutionError(
                f"Secret payload for {secret_ref} must be valid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise SecretResolutionError(f"Secret payload for {secret_ref} must be a JSON object.")
        return payload

    @staticmethod
    def env_name_for_ref(secret_ref: str) -> str:
        name = re.sub(r"^secret://", "", secret_ref.strip(), flags=re.IGNORECASE)
        name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
        if not name:
            raise SecretResolutionError("secret_ref must not be blank.")
        return f"DATAGENT_SECRET_{name}"
