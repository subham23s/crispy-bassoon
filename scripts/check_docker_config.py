"""Validate Compose structure without requiring Docker to be installed."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    compose = ROOT / "docker-compose.yml"
    result = {"docker_available": bool(shutil.which("docker")), "compose_file": compose.exists(), "yaml_parse": "not_attempted", "checks": {}, "warnings": []}
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(compose.read_text(encoding="utf-8"))
        result["yaml_parse"] = "ok"
        services = data.get("services", {}) if isinstance(data, dict) else {}
        result["checks"] = {
            "backend_and_frontend": all(name in services for name in ("backend", "frontend")),
            "infra_services": all(name in services for name in ("postgres", "redis", "neo4j")),
            "persistent_volumes": all(name in (data.get("volumes") or {}) for name in ("postgres_data", "redis_data", "neo4j_data")),
            "postgres_healthcheck": "healthcheck" in services.get("postgres", {}),
            "redis_healthcheck": "healthcheck" in services.get("redis", {}),
            "neo4j_healthcheck": "healthcheck" in services.get("neo4j", {}),
        }
    except ImportError:
        result["yaml_parse"] = "blocked_missing_PyYAML"
        result["warnings"].append("Install PyYAML or Docker Compose to validate the full Compose schema.")
    except Exception as exc:
        result["yaml_parse"] = "error"
        result["warnings"].append(str(exc))
    print(json.dumps(result, indent=2))
    checks = result.get("checks", {})
    raise SystemExit(0 if result["compose_file"] and result["yaml_parse"] == "ok" and checks and all(checks.values()) else 2)


if __name__ == "__main__":
    main()
