# MEMORY.md — Example Project
Last updated: 2026-07-20T09:15:00Z

## Tier 3 — Domain Rules & User Preferences
- Always use named exports, never default exports, in this codebase.
- Never log raw token values or PII, in any environment, including local dev.

## Tier 2 — System Architecture & Decisions
- [ADR-005] 2026-07-19 — Adopted refresh-token rotation on top of JWT auth. Rationale: short-lived access tokens without rotation forced re-logins too often for the client's UX target. Status: active. Source: 2026-07-19 — refresh flow design session.
- [ADR-006] 2026-07-19 — Replaced session-cookie auth with JWT-based auth. Rationale: needed stateless auth to support the planned horizontal scaling. Status: active (supersedes ADR-003). Source: 2026-07-19 — auth architecture review.
- [ADR-003] 2026-07-13 — Session-cookie auth. Rationale: fastest path to a working login flow for the MVP. Status: superseded (by ADR-006). Source: 2026-07-13 — MVP kickoff. Last referenced: 2026-07-19.

## Tier 1 — Active Execution
- [done] Add refresh-token rotation middleware (gate verified)
- [in_progress] Add rate limiting to the refresh-token endpoint (source: 2026-07-20 — refresh flow design session) (gate pending: npm test -- rate-limit.spec.ts)
- [todo] Write integration tests for the rotation flow
- [blocked] Deploy to staging — reason: waiting on infra team to provision the Redis instance for token blocklisting

## Compressed Changelog
- [2026-07-13 to 2026-07-18]: Completed JWT auth migration, including refresh-token rotation and a login race-condition fix.
- [2026-07-13 to 2026-07-18]: Replaced session-cookie auth (ADR-003) with JWT-based auth (ADR-006).
