# External Agent Quality Loop Implementation Plan

> For agentic workers: execute inline following superpowers:executing-plans; user requested fewer subagents. One final independent review only if useful.

**Goal:** 外部 Coding Agent 能按需读取用户共同设计并发布的内置 Skill，向平台提交可审阅的评测集与质量报告，由用户确认版本。用户明确要求不由助手独自编写 Skill 的方法内容。
**Architecture:** MCP stdio → FastAPI → shared dataset/quality service → SQLite WAL。网页消费相同服务，保持示例隔离。
**Tech Stack:** Existing Next.js/TypeScript/FastAPI/SQLite + official mcp 2.3.0 (Python 3.11+).
**Spec:** docs/EXTERNAL_AGENT.md and the user's 2026-11-06 clarified inbound-agent workflow.

## Global Constraints
- Chinese UI, existing Design System; no paid models; no Harness changes.
- Normal database never receives verification fixtures. Current folder is not a Git repository; no worktree/commit automation applies.
- User already authorized implementation; no repeated design approval or per-task handoff.

## Review Focus
- Hash/report or case references cannot cross drafts.
- Partial review, blockers, stale reports and stale base versions cannot silently publish.
- Duplicate request IDs are idempotent only for identical payloads.
- Project switching must not show or approve the previous project's draft.
- Connection claims distinguish tool traffic from mere service availability.

## Tasks

- [x] Backend RED → GREEN: `tests/test_quality.py`; strict contracts in `lab/quality_schemas.py`, deterministic checks in `lab/quality_checks.py`, transactional persistence in `lab/datasets.py`, migration 002 and backward-compatible migration runner, routes in `lab/quality_routes.py`. Test immutable versions, migration data preservation, evidence binding, partial/stale review, concurrent base, idempotency.
- [x] External tools: `lab/mcp_server.py`, `lab/integration.py`. Official SDK tools use HTTP; test actual stdio discovery, structured errors and round trip with isolated local API. Expose JSON Schema contracts, not Skill instructions.
- [x] Skill infrastructure only: `lab/skills.py`, migration 003, `components/skills.tsx`; catalog item for dataset design has no authored content. User-authored immutable drafts and manual publication, published-only discovery, exact source version/hash binding. Test draft cannot be fetched as ready, content snapshots retained and invalid provenance rejected.
- [x] UI: `components/dataset-workspace.tsx`, `components/quality-detail.tsx`, `components/connections.tsx`; extend API/types and route real datasets to the new page. Verify project selection, evidence navigation, stale approval errors, decision flow and narrow layout.
- [x] Integration: update PRODUCT/FRAMEWORK/README/VERIFICATION; build, backend/full domain tests, isolated browser verification, final review; restart delivery services on existing user DB with schema migration. Final: 27 backend tests passed / 1 skipped; 11 frontend tests passed; 8 new UI checks passed; 9-page build passed; read-only delivery smoke passed with no user-data fixtures.
