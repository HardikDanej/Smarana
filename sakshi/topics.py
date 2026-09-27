"""
A fixed, generic topic taxonomy used two ways:

1. As the criteria for a single Laya "choice" question (see laya_score.py),
   asked once per ADR, out of band, whenever MEMORY.md changes. Laya returns
   a full probability distribution over these topics for that ADR's text —
   not just the top pick — and that distribution is cached to disk.

2. As a zero-latency, keyword-seed fallback classifier (`classify_text`) used
   for two things: scoring a sub-agent's dispatch prompt at SubagentStart
   (always — a live prompt can never be pre-scored), and scoring an ADR when
   no cached Laya score exists for it yet, or `laya` was never installed.

This module makes no model calls and has no dependency on `laya` itself —
only laya_score.py imports that, and only when it actually runs. Everything
here is pure stdlib, same as memory.py.

The taxonomy is a starting set for general software projects. It is not
exhaustive, and a project whose ADRs don't fit any of these topics simply
gets no similarity boost from this layer — ranking then falls back to the
plain keyword overlap memory.py already did before this existed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sakshi.memory import keywords
from sakshi.store import Store

GLOBAL_SESSION = "_global"
CACHE_KEY = "adr_topics"

TOPICS: dict[str, dict] = {
    "auth_identity": {
        "description": "Authentication, authorization, sessions, tokens, login, or permissions.",
        "seeds": {"auth", "authentication", "authorization", "login", "logout", "session",
                  "sessions", "token", "tokens", "jwt", "oauth", "sso", "permission",
                  "permissions", "role", "roles", "rbac", "identity", "credential",
                  "credentials", "password", "passwords", "mfa", "refresh"},
    },
    "data_storage": {
        "description": "Databases, schemas, data models, migrations, caching layers, or persistence.",
        "seeds": {"database", "databases", "schema", "schemas", "migration", "migrations",
                  "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis", "cache",
                  "caching", "storage", "table", "tables", "index", "indexes", "orm",
                  "query", "queries", "persistence"},
    },
    "api_contracts": {
        "description": "API design, endpoints, request/response contracts, versioning, or protocols.",
        "seeds": {"api", "apis", "endpoint", "endpoints", "rest", "restful", "graphql",
                  "grpc", "contract", "contracts", "versioning", "payload", "payloads",
                  "request", "response", "webhook", "webhooks", "openapi", "swagger"},
    },
    "frontend_ui": {
        "description": "Frontend architecture, UI components, styling, or client-side rendering.",
        "seeds": {"frontend", "ui", "ux", "component", "components", "react", "vue",
                  "angular", "css", "styling", "render", "rendering", "screen", "screens",
                  "layout", "design-system"},
    },
    "backend_services": {
        "description": "Backend services, business logic, server architecture, or service boundaries.",
        "seeds": {"backend", "service", "services", "server", "microservice",
                  "microservices", "controller", "handler", "module", "modules"},
    },
    "infra_deployment": {
        "description": "Infrastructure, hosting, deployment pipelines, containers, or environment config.",
        "seeds": {"infrastructure", "infra", "deploy", "deployment", "deployments",
                  "docker", "container", "containers", "kubernetes", "hosting", "servers",
                  "pipeline", "pipelines", "environment", "staging", "production", "cloud",
                  "aws", "azure", "gcp", "terraform"},
    },
    "testing_qa": {
        "description": "Automated tests, test coverage, QA process, or verification strategy.",
        "seeds": {"test", "tests", "testing", "unittest", "pytest", "jest", "coverage",
                  "qa", "mock", "mocks", "fixture", "fixtures", "assertion", "assertions",
                  "regression"},
    },
    "performance": {
        "description": "Performance, latency, throughput, scalability, or resource-usage concerns.",
        "seeds": {"performance", "latency", "throughput", "scalability", "scale",
                  "optimization", "optimize", "bottleneck", "slow", "benchmark",
                  "benchmarks", "load"},
    },
    "security": {
        "description": "Security posture, vulnerabilities, encryption, access control, or compliance.",
        "seeds": {"security", "vulnerability", "vulnerabilities", "encryption", "encrypt",
                  "exploit", "exploits", "csrf", "xss", "injection", "sanitize",
                  "sanitization", "compliance", "audit", "secrets", "secret"},
    },
    "integrations_third_party": {
        "description": "Third-party integrations, external APIs, vendor services, or partner systems.",
        "seeds": {"integration", "integrations", "vendor", "vendors", "external", "sdk",
                  "plugin", "plugins", "connector", "connectors", "stripe", "twilio",
                  "sendgrid"},
    },
    "build_tooling": {
        "description": "Build systems, package management, tooling, linting, or developer workflow.",
        "seeds": {"build", "bundler", "webpack", "vite", "npm", "yarn", "pnpm", "package",
                  "packages", "lint", "linting", "formatter", "tooling", "tsconfig",
                  "babel", "monorepo"},
    },
    "messaging_async": {
        "description": "Message queues, event buses, background jobs, or asynchronous processing.",
        "seeds": {"queue", "queues", "kafka", "rabbitmq", "sqs", "event", "events",
                  "async", "asynchronous", "worker", "workers", "job", "jobs", "pubsub",
                  "broker"},
    },
    "observability_monitoring": {
        "description": "Logging, monitoring, alerting, tracing, or error-reporting infrastructure.",
        "seeds": {"logging", "logs", "monitoring", "alert", "alerts", "alerting", "metric",
                  "metrics", "trace", "tracing", "observability", "sentry", "datadog",
                  "grafana", "prometheus"},
    },
    "documentation_process": {
        "description": "Documentation, team process, coding standards, or project conventions.",
        "seeds": {"documentation", "docs", "readme", "changelog", "convention",
                  "conventions", "standard", "standards", "process", "workflow",
                  "contributing"},
    },
}


def hash_text(text: str) -> str:
    """Cache-invalidation key: if an ADR's text changes, its cached Laya score
    is stale and select_adrs() must fall back to keyword-only for it."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def laya_criteria() -> dict[str, str]:
    """The `criteria` block for a Laya "choice" question, same shape as
    tier_screen.py's TIER_QUESTION."""
    return {key: cfg["description"] for key, cfg in TOPICS.items()}


def classify_text(text: str) -> dict[str, float]:
    """Zero-latency topic distribution from keyword-seed overlap alone.

    Returns {} when nothing matched (no signal, not "topic X at zero" for
    every topic) so callers can tell "no opinion" from "actively unrelated".
    """
    words = keywords(text)
    if not words:
        return {}
    raw = {topic: len(words & cfg["seeds"]) for topic, cfg in TOPICS.items()}
    total = sum(raw.values())
    if total == 0:
        return {}
    return {topic: count / total for topic, count in raw.items() if count}


def topic_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Dot product of two topic distributions. 0.0 if either is empty/unknown."""
    if not a or not b:
        return 0.0
    return sum(a.get(k, 0.0) * b.get(k, 0.0) for k in set(a) | set(b))


def load_adr_topics(sakshi_dir: Path) -> dict[str, dict]:
    """{adr_id: {"hash": ..., "topics": {...}, "scored_at": ...}}, or {} if
    laya_score.py has never run (or `laya` isn't installed) — the everyday
    case for a project that hasn't opted into this. A plain, lock-free read
    is safe here because writes always go through Store's atomic replace.
    """
    import json

    path = Store(sakshi_dir).path_for(GLOBAL_SESSION, CACHE_KEY)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    adrs = data.get("adrs") if isinstance(data, dict) else None
    return adrs if isinstance(adrs, dict) else {}
