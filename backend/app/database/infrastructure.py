"""Select real optional services and retain an honest SQLite fallback."""
from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from typing import Any

from app.config import Settings

from .health import ServiceHealth, unavailable
from .neo4j_adapter import Neo4jAdapter
from .postgres import PostgresRepository
from .redis_adapter import RedisAdapter
from .sqlite import SQLiteRepository


class Infrastructure:
    """Own repository/client lifecycles and expose one health contract."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.repository: Any
        self._postgres: PostgresRepository | None = None
        self.database_requested = not config.database_url.lower().startswith("sqlite:")
        self.database_fallback_reason = ""
        self.database = self._build_repository()
        self.redis = RedisAdapter(config.redis_url, config.service_connect_timeout)
        self.neo4j = Neo4jAdapter(config.neo4j_uri, config.neo4j_username, config.neo4j_password, config.service_connect_timeout)

    @staticmethod
    def sqlite_path(database_url: str, data_dir: Path) -> str:
        if database_url.startswith("sqlite:///"):
            return database_url.removeprefix("sqlite:///")
        return str(data_dir / "cybersecra.db")

    def _build_repository(self) -> ServiceHealth:
        if not self.database_requested:
            self.repository = SQLiteRepository(self.sqlite_path(self.config.database_url, self.config.data_dir))
            return ServiceHealth("database", True, True, "sqlite-fallback", reason="SQLite is the configured local repository")
        try:
            self._postgres = PostgresRepository(
                self.config.database_url,
                pool_size=self.config.db_pool_size,
                max_overflow=self.config.db_max_overflow,
                timeout=self.config.service_connect_timeout,
            )
            self.repository = self._postgres
            return ServiceHealth("database", True, True, "postgresql-pgvector")
        except Exception as exc:
            # Catch optional dependency and connectivity failures, but preserve
            # the reason in health rather than masking it.
            self.database_fallback_reason = f"PostgreSQL unavailable: {type(exc).__name__}: {exc}"
            self.repository = SQLiteRepository(str(self.config.data_dir / "cybersecra.db"))
            return unavailable("database", True, self.database_fallback_reason)

    def health(self) -> dict[str, Any]:
        database = self.database
        if self._postgres is not None:
            database = replace(self._postgres.health_check(), name="database")
        redis = self.redis.health_check()
        graph = self.neo4j.health_check()
        services = {item.name: item.to_dict() for item in (database, redis, graph)}
        degraded = any(item["degraded"] for item in services.values())
        reasons = [f"{name}: {item['reason']}" for name, item in services.items() if item["degraded"] and item["reason"]]
        return {
            "mode": "degraded" if degraded else "production-ready",
            "degraded": degraded,
            "reasons": reasons,
            "repository_backend": getattr(self.repository, "backend_name", "sqlite"),
            "services": services,
        }

    def close(self) -> None:
        self.redis.close()
        self.neo4j.close()
        close = getattr(self.repository, "close", None)
        if close is not None:
            close()
