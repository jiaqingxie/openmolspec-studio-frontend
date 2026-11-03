from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

DEVELOPMENT_IDENTITIES = {"researcher": "模拟研究员", "analyst": "模拟分析员"}


@dataclass(frozen=True)
class Settings:
    database: str = field(default_factory=lambda: os.getenv("OPENMOLSPEC_DATABASE_URL", ""), repr=False)
    internal_key: str = field(default_factory=lambda: os.getenv("OPENMOLSPEC_INTERNAL_KEY", ""), repr=False)
    environment: str = field(default_factory=lambda: os.getenv("OPENMOLSPEC_ENV", "production"))
    mock_enabled: bool = field(default_factory=lambda: os.getenv("OPENMOLSPEC_MOCK_SSO", "0") == "1")
    session_hours: int = field(default_factory=lambda: int(os.getenv("OPENMOLSPEC_SESSION_HOURS", "24")))
    mcp_local_url: str | None = field(default_factory=lambda: os.getenv("OPENMOLSPEC_MCP_LOCAL_URL") or None)
    mcp_cloud_url: str | None = field(default_factory=lambda: os.getenv("OPENMOLSPEC_MCP_CLOUD_URL") or None)
    upload_dir: Path = field(default_factory=lambda: Path(os.getenv("OPENMOLSPEC_UPLOAD_DIR", ".openmolspec/uploads")))
    chemistry_url: str = field(default_factory=lambda: os.getenv("OPENMOLSPEC_CHEMISTRY_URL", "http://127.0.0.1:8001").rstrip("/"))
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""), repr=False)
    base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"))
    model: str = field(default_factory=lambda: os.getenv("OPENMOLSPEC_LLM_MODEL", ""))
    provider_timeout: float = 120.0
    max_output_tokens: int = field(default_factory=lambda: int(os.getenv("OPENMOLSPEC_MAX_OUTPUT_TOKENS", "4096")))
    token_limit: int = field(default_factory=lambda: int(os.getenv("OPENMOLSPEC_RUN_TOKEN_LIMIT", "64000")))
    calculation_timeout: float = field(default_factory=lambda: float(os.getenv("OPENMOLSPEC_CALCULATION_WAIT_SECONDS", "1800")))
    max_upload_size: int = 10 * 1024 * 1024

    def validate_startup(self):
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("OPENMOLSPEC_ENV must be development, test, or production")
        if self.mock_enabled and self.environment == "production":
            raise ValueError("Mock SSO is only allowed in development or isolated tests")
        if not self.database.strip() or not self.internal_key.strip():
            raise ValueError("OPENMOLSPEC_DATABASE_URL and OPENMOLSPEC_INTERNAL_KEY are required")
        for url in (self.mcp_local_url, self.mcp_cloud_url):
            if url:
                parsed = urlsplit(url)
                if (parsed.scheme not in {"http", "https"} or not parsed.hostname or
                        parsed.username is not None or parsed.query or parsed.fragment):
                    raise ValueError("MCP endpoint settings require HTTP(S) URLs without credentials or query parameters")

    @property
    def configured(self) -> bool:
        return bool(self.model.strip() and (self.api_key.strip() or self.base_url != "https://api.openai.com/v1"))
