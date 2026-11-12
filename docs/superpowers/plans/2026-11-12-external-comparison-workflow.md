# External Comparison Workflow Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. No model calls or subagent analysis are authorized for this delivery.

**Goal:** An external Agent can read a pinned workflow and paired case materials, submit case analyses and a final report, and show evidence-backed changes and development suggestions in the local platform.

**Architecture:** Add a comparison domain alongside existing imports, judgments and rechecks. Immutable source snapshots and append-only external reports use SQLite; HTTP and MCP expose the same services. A comparison-scoped simulated B is visibly separate from imported real runs. Existing scoring code and original archives remain unchanged.

**Tech Stack:** Existing FastAPI/Pydantic/SQLite, MCP stdio, Next.js client components and CSS modules; no new runtime dependencies.

**Spec:** Approved scope in this chat and the reviewed workflow draft; final workflow and interface contract are maintained with this implementation.

## Global Constraints

- No model calls, Agent runs or evaluation reruns. Offline scripted responses validate protocol and display only.
- No edits to existing graders, grading Skill versions, task definitions or original archives.
- External Agent initiates analysis; platform does not launch Codex CLI.
- Simulation labels are derived by the server and persist on overview, case evidence and reports.
- Collection completeness and evidence sufficiency remain separate; final reports cannot omit planned cases.
- Analysis reports do not replace historical scores. Source changes block new analysis but do not erase saved history.

## Review Focus

- Missing/changed task pairs cannot become pass-to-fail capability regressions.
- Evidence references are scoped to the planned case, version and source; excerpts come from hash-verified materials.
- Idempotency, stale case revisions and stale finalization cannot silently replace reports.
- Simulated B or scripted analysis cannot be presented as measured capability gains.
- Unknown metrics and absent B remain unknown; report completion does not imply analytical validity.

## Tasks

- [x] 1. Add failing API tests covering comparison creation, source materials, submissions, coverage and provenance. Run them and observe missing routes.
- [x] 2. Implement migration006 and focused comparison schemas/materials/service/routes. Preserve existing APIs. Run focused and full backend tests.
- [x] 3. Add MCP material/report tools and formal workflow package plus output schema. Validate actual stdio roundtrip without a model.
- [x] 4. Add comparison workspace, case drilldown, development suggestions and immutable report selection. Test metric/coverage semantics, typecheck and build.
- [x] 5. Seed one local offline demonstration from real U05 and a comparison-only simulated B. Verify original archive hashes, read live platform, and inspect desktop browser results.

## File Responsibilities

- backend/lab/comparisons/: schemas.py defines inputs; materials.py pins/reads sources; service.py persists analyses; routes.py exposes HTTP.
- backend/lab/migrations/006_comparisons.sql: comparison plans, case reports and final reports.
- backend/lab/main.py, db.py, integration.py, mcp_server.py: registration and external access only.
- backend/tests/test_comparisons.py: meaningful integrity and lifecycle tests; MCP roundtrip extends existing protocol checks.
- apps/web/lib/comparisons.ts and components/comparison-*.tsx/.module.css: presentation contracts, queue, evidence and reports.
- skills/agent-version-comparison-workflow/: workflow, machine-readable output schemas and example.
- scripts/seed_comparison_demo.py: explicit offline fixture, local Skill publication and scripted report submission; never runs an Agent or checker.

## Ledger

- Ruling: Work in the existing user-selected clean checkout at fb18c44, preserving the established local service location. Builds use isolated copies.
- Ruling: Do not spawn an independent model reviewer because the user explicitly prohibited model calls; conduct a scoped manual review and record verification.
- Ruling: Use existing recorded grades and raw resource counters. New semantic observations belong to external analysis and never change acceptance scores.
- Verified: 70 backend tests passed, 1 existing Windows symlink test skipped; 21 frontend tests passed; typecheck, production build and Skill structure validation passed.
- Manual review: API source and revision guards, MCP registration, immutable history, simulation labels and UI loading states inspected. No model reviewer was invoked.
- Corrected during verification: Skill API trims surrounding text, so packaging uses the same normalization; original file drift is checked independently of the manifest; U05 duration consistently uses archived case metrics.
- Browser acceptance: summary is visible before detailed metadata, development suggestions link to U05, event97/98 preview retains the failure, and old/new report selection preserves frozen case analyses. Console errors: none.
- Offline receipt: comparison 06a91baa-325a-47d1-9070-b19d8393dade, report caf5d3a0-8d35-4edf-be1c-efd016170b5e. All1099 original archive files unchanged; model and evaluation requests:0. This proves the protocol/display chain, not an improvement in the evaluated Agent.

## Authorized retro refinement · 2026-11-13

- [x] Read and pin the upstream retro reference; inspect the current workflow and existing uncommitted changes.
- [x] Add mechanism/gap investigation, target component and minimum-action choices to method0.1.1; preserve grading and report schemas.
- [x] Package and publish an additional Skill version, retaining the original version and reports.
- [x] Read U05 through actual MCP and submit a baseline-only scripted report; B remains missing, no model/evaluation/checker run.
- [x] Run18 scoped protocol/Skill tests and the structure validator; check the original1099 archive files and53 protected file hashes.

Ruling: User prohibition on model calls takes precedence over the writing-skills model-pressure-test workflow. Verify structure and protocol offline; model behavior quality remains unverified. No subagents invoked. Final baseline comparison915328f1-9bf6-48ce-b10d-cf11b32d5464, reportede8d637-01b9-453c-b66b-7d1dac1ba687.
