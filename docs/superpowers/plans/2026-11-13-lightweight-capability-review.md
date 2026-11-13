# Lightweight Capability Review Implementation Plan

**Goal:** A lightweight analysis Skill consumes a program-prepared packet and submits one analysis document; the platform shows deterministic metric changes, evidence and development advice over the existing20 archived pairs.

**Architecture:** Add a metric registry and review adapter alongside existing comparison services. The program owns extraction, statistics, evidence references, stable request identities and atomic report submission. Existing comparison reports remain readable; new reports carry a versioned metric section. No new scoring or model runner.

**Spec:** User-approved lightweight Skill draft and this chat's explicit implementation scope. Retro refinement targets the project's adaptation of Matt Pocock retro unless corrected by the user.

## Global Constraints

- No model calls, evaluation reruns, original grading changes or GitHub push.
- Preserve existing uncommitted performance changes, archives and historical reports.
- Metrics with no confirmed rubric remain visible as unassessed; collection completeness is separate from metric coverage.
- Registry groups existing same-rule checks by case and keeps denominators, gains and regressions. Resource cost is not a capability score.
- Lightweight reports do not require the analyst to manage UUIDs, hashes, revisions or per-case HTTP submissions.
- Model-based Skill behavior tests and subagent review are excluded by the user's no-model requirement; verify offline structure, fixtures and actual protocol instead.

## Review Focus

- Missing B, changed requirements, unknown verdicts and legacy compaction telemetry must not create false regressions or zeros.
- A changed source or stale prepared packet cannot silently replace newer work.
- Identical submissions return the same receipt; errors before acknowledgement do not justify a new request identity.
- Invalid advice/evidence rolls back all case and final writes; report references are program-generated from verified materials.
- Offline program advice is labelled as such; platform validation does not prove semantic causes.

## Tasks

- [x] 1. Pin current working state and add failing tests for registry counts, missing coverage, packet validity, atomic/idempotent submissions and source drift.
- [x] 2. Implement metric aggregation, compact preparation/read interfaces, one-shot submission and CLI; preserve legacy APIs and performance work.
- [x] 3. Publish the lightweight Skill and refine retro guidance; replace schema-heavy packaging with concise instructions and program usage.
- [x] 4. Add metric-first platform presentation with case/evidence drilldown; verify types, tests and isolated build.
- [x] 5. Validate actual20 archives offline end-to-end, preserve archive/grade hashes, inspect the platform, and record receipts. No push.

## Ledger

- Starting local commit:09da00f. Existing dirty files include migration007, request-scoped source checks and report-loading changes; preserve them.
- Use additive modules and small integrations in the existing checkout. Build outside the live app directory. Do not stop an active scoring job.
- Delivered report:70228db5-c312-4139-8677-778bc67c4aaa, comparison:e4438e29-da18-4c37-afd2-3fa827444ffd. Skill version:fbc4b4a0-71c6-459e-96cf-83c9db9dc3d4, method0.2.0,2583characters.
- Verification:100 backend tests passed/1 Windows symlink test skipped;32 frontend tests passed;isolated production build passed. Actual stdio and CLI exercised, real20 retry returned same receipt. Browser inspected overview,U05 evidence/task drilldown and3 recommendations; no console errors.
- All7791 original archive files unchanged by SHA-256. Every preexisting comparison,case report,final report,Skill version,judgment,check run andchecker binding row preserved. Added20 case reports,1 final report,1 Skill version; no model/evaluation/scorer runs. No commit or push during this task.
- PRODUCT.md uses an older context format; this narrow refinement followed the existing DESIGN.md and did not expand into an init/document migration. Model-based Skill behavior and causal quality remain untested by explicit user constraint.
