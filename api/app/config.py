"""Runtime configuration.

Every secret is a :class:`~pydantic.SecretStr` so it never lands in a log line, a
traceback, or a ``/health`` response by accident. Placeholder values live in
``infra/.env.example`` - never real credentials.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "ci", "prod"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PROTRIX_",
        env_file=(".env", "../.env", "../infra/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = "local"
    log_level: str = "INFO"
    service_name: str = "api"

    database_url: str = "postgresql+psycopg://protrix:protrix@localhost:5432/protrix"
    redis_url: str = "redis://localhost:6379/0"

    # Mock dev identity. HS256 shared secret - placeholder only.
    dev_identity_enabled: bool = True
    dev_jwt_secret: SecretStr = SecretStr("dev-only-not-a-real-secret-change-me")
    dev_jwt_issuer: str = "protrixplus-dev-identity"
    dev_jwt_ttl_seconds: int = 3600

    # Auth0 OIDC. Empty values deliberately keep local/CI on dev identity.
    auth0_issuer: str = ""
    auth0_audience: str = ""
    auth0_role_claim: str = "https://protrixplus/role"
    auth0_email_claim: str = "https://protrixplus/email"
    auth0_name_claim: str = "https://protrixplus/name"

    # Mock webhook ingress auth (stands in for a signed TradingView source).
    webhook_shared_secret: SecretStr = SecretStr("dev-webhook-token-change-me")
    # Secret path segment for direct TradingView alert delivery. This is
    # separate from the simulator header secret so local tooling keeps working.
    tradingview_webhook_secret: SecretStr = SecretStr("")

    # Razorpay is intentionally disabled until test/live keys are configured.
    # The public key may go to Checkout; secrets never leave the server.
    razorpay_key_id: str = ""
    razorpay_key_secret: SecretStr = SecretStr("")
    razorpay_webhook_secret: SecretStr = SecretStr("")

    # Redis stream the worker consumes signal events from.
    signal_stream: str = "protrix.signals.v1"
    signal_consumer_group: str = "protrix-workers"

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    def secret_values(self) -> list[str]:
        """All secret strings, for the log-redaction filter."""
        values = [
            self.dev_jwt_secret.get_secret_value(),
            self.webhook_shared_secret.get_secret_value(),
            self.tradingview_webhook_secret.get_secret_value(),
            self.razorpay_key_secret.get_secret_value(),
            self.razorpay_webhook_secret.get_secret_value(),
        ]
        # Also redact any password embedded in the DB / Redis URLs.
        for url in (self.database_url, self.redis_url):
            if "@" in url and "://" in url:
                creds = url.split("://", 1)[1].split("@", 1)[0]
                if ":" in creds:
                    values.append(creds.split(":", 1)[1])
        return [v for v in values if v]


@lru_cache
def get_settings() -> Settings:
    return Settings()
