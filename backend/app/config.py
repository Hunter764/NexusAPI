"""
NexusAPI configuration module.
Loads all settings from environment variables using pydantic-settings.
"""

from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://nexus:nexus_secret@localhost:5432/nexusapi",
        description="PostgreSQL async connection string",
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def format_database_url(cls, v: Any) -> Any:
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgresql://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            if "?" in v:
                from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
                parsed = urlparse(v)
                query_params = dict(parse_qsl(parsed.query))
                
                if query_params.get("sslmode") == "require":
                    query_params["ssl"] = "require"
                
                query_params.pop("sslmode", None)
                query_params.pop("channel_binding", None)
                query_params.pop("options", None)
                
                new_query = urlencode(query_params)
                v = urlunparse(parsed._replace(query=new_query))
        return v

    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )

    # JWT
    JWT_SECRET_KEY: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for JWT signing",
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRY_HOURS: int = Field(default=24)

    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(
        default="", description="Google OAuth client ID"
    )
    GOOGLE_CLIENT_SECRET: str = Field(
        default="", description="Google OAuth client secret"
    )
    GOOGLE_REDIRECT_URI: str = Field(
        default="http://localhost:8000/auth/callback"
    )

    # Application
    APP_NAME: str = Field(default="NexusAPI")
    APP_ENV: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=60, description="Max requests per minute per organisation"
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Module-level convenience — used throughout the app
settings = get_settings()
