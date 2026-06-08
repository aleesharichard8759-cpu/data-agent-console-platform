from functools import lru_cache

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_name: str = "Data Governance Agent Runtime"
    app_version: str = "0.1.0"
    environment: str = "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()

