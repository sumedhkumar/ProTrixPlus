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

    # Mock webhook ingress auth (stands in for a signed TradingView source).
    webhook_shared_secret: SecretStr = SecretStr("dev-webhook-token-change-me")
    # Secret path segment for direct TradingView alert delivery. This is
    # separate from the simulator header secret so local tooling keeps working.
    tradingview_webhook_secret: SecretStr = SecretStr("")

    # Redis stream the worker consumes signal events from.
    signal_stream: str = "protrix.signals.v1"
    signal_consumer_group: str = "protrix-workers"

    # Outbound email (trial temp-password, payment-proof admin notification,
    # forgot-password reset link). "mock" (default) never sends real mail -
    # local/CI safety. "smtp" is Gmail by default (see infra/.env.example).
    # "brevo" sends over HTTPS instead, which is what production uses: Render
    # blocks outbound SMTP ports on free web services, so "smtp" cannot
    # deliver from there. Both honour smtp_from_name / smtp_from_address.
    email_backend: Literal["smtp", "brevo", "mock"] = "mock"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_name: str = "ProTrixPlus"
    smtp_from_address: str = ""
    # Brevo API key (email_backend="brevo"). The sender address above must be
    # verified under Senders in the Brevo dashboard or sends are rejected.
    brevo_api_key: SecretStr = SecretStr("")
    # Where payment-proof (UTR) submissions get emailed for human review.
    admin_notify_email: str = ""
    # Used to build the password-reset link sent to a user's inbox.
    frontend_base_url: str = "http://localhost:3000"

    # Manual-payment instructions shown on /subscribe before a UTR submission.
    # All optional - the frontend shows a "to be added" placeholder state for
    # whichever of these are unset, per docs/FULL-BUILD-PLAN.md decision #4
    # (no payment gateway; the customer transfers out-of-band).
    payment_bank_account_name: str = ""
    payment_bank_account_number: str = ""
    payment_bank_ifsc: str = ""
    payment_bank_name: str = ""
    payment_upi_id: str = ""
    payment_qr_code_url: str = ""

    # MetaApi.cloud (ADR-001) - same token the worker's MetaApiExecutionAdapter
    # uses, so the API can also make its own calls (live balance, real
    # self-service account provisioning) without needing a second credential.
    metaapi_token: SecretStr = SecretStr("")
    metaapi_default_region: str = "london"

    # Encryption key for RealCredentialVault (api/app/vault/real.py). Unused
    # today - nothing constructs that vault yet - but read from here once
    # something does. Generate with Fernet.generate_key().
    vault_encryption_key: SecretStr = SecretStr("")

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    def secret_values(self) -> list[str]:
        """All secret strings, for the log-redaction filter."""
        values = [
            self.dev_jwt_secret.get_secret_value(),
            self.webhook_shared_secret.get_secret_value(),
            self.tradingview_webhook_secret.get_secret_value(),
            self.smtp_password.get_secret_value(),
            self.brevo_api_key.get_secret_value(),
            self.metaapi_token.get_secret_value(),
            self.vault_encryption_key.get_secret_value(),
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
