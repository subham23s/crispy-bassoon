"""Application configuration loaded from environment variables.

The default configuration is intentionally local-first: SQLite and the bundled
curated corpus make the evidence pipeline runnable without external services.
PostgreSQL, Redis, Neo4j, and an LLM provider are opt-in integrations.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Load the repository .env without overriding explicitly exported values."""
    dotenv_path = ROOT_DIR / ".env"
    if not dotenv_path.is_file():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _jwt_secret() -> str:
    configured = os.getenv("JWT_SECRET", "").strip()
    if configured and configured != "replace-with-a-long-random-secret":
        if os.getenv("ENVIRONMENT") == "production" and len(configured) < 32:
            raise RuntimeError("Production JWT_SECRET must contain at least 32 characters")
        return configured
    if os.getenv("ENVIRONMENT", "development") == "production":
        raise RuntimeError("JWT_SECRET must be configured in production")
    # Stable local authentication without shipping a shared signing secret.
    path = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data"))) / ".jwt_secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text(encoding="utf-8").strip()
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        value = secrets.token_urlsafe(48)
        handle.write(value)
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "CyberSecRA-X")
    environment: str = os.getenv("ENVIRONMENT", "development")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{ROOT_DIR / 'data' / 'cybersecra.db'}")
    redis_url: str = os.getenv("REDIS_URL", "")
    neo4j_uri: str = os.getenv("NEO4J_URI", "")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "")
    service_connect_timeout: float = float(os.getenv("SERVICE_CONNECT_TIMEOUT", "0.5"))
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    llm_provider: str = os.getenv("LLM_PROVIDER", "none")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "tfidf-lite")
    reranker_model: str = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    jwt_secret: str = _jwt_secret()
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    background_upload_bytes: int = int(os.getenv("BACKGROUND_UPLOAD_BYTES", str(2 * 1024 * 1024)))
    data_dir: Path = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data")))
    demo_mode: bool = _bool("DEMO_MODE", True)
    cors_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()
    )


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "raw").mkdir(parents=True, exist_ok=True)
(settings.data_dir / "processed").mkdir(parents=True, exist_ok=True)
