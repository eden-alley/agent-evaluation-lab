# U05 saved-delivery rechecking implementation plan

> For agentic workers: execute inline with superpowers:executing-plans; use TDD and a fresh final review.

**Goal:** Bind U05 to a versioned, trusted checker and independently check its saved delivery without rerunning the Agent or changing its archive.

**Architecture:** Add immutable checker bindings and separate check-run records to SQLite. A registered checker reads verified archive inputs, compares original evidence, and runs frozen tests in disposable copies through a separately versioned Windows native sandbox adapter. Keep the original archive and existing archive/mock Judge flows separate. Add a small case-page control for binding, starting, viewing and comparing check records.

**Tech stack:** Existing FastAPI, SQLite, Python stdlib, React/Next.js. No new dependencies.

**Spec:** User-approved design in this chat: give each task a fixed checking method, save deliveries, recheck old deliveries independently, retain old/new judgments and evidence. U05 is the sole pilot.

## Global constraints

- Existing uncommitted work is preserved; baseline copies are under the current chat's work/u05-recheck-before directory. Continue in the existing user-selected project checkout.
- No Agent/model calls, no Harness edits, no task or archive changes, no importing executable code from archives. Native sandbox failure never falls back to host execution.
- Bind task/check contract, source digest, checker code/tests digest and interpreter/sandbox identities. Check outputs are separate from Agent execution and from historical Judge labels.
- Original successful self-testing is proved only by original events and final source hashes. External tests cannot establish it. Missing semantic evidence stays unknown.
- Scope checks happen before trusted tests replace the public-test files in disposable copies. New grading results never replace historical automatic or reviewed scores.

## Review focus

- Corrupt or incomplete snapshot and stale bindings must stop checking, not count as Agent failures.
- Same request is idempotent; changed payload under the same request ID is rejected; service restart marks interrupted runs explicitly.
- Failing tests and broken test infrastructure must stay distinct; zero discovered tests cannot pass.
- New checks cannot execute temporary Agent scripts or reference fixes; only registered test suites run, in the existing native sandbox.
- UI async responses must not mix cases or historical and new checks; old run counts stay unchanged.

## Tasks

- [x] Add failing backend tests for immutable binding, rechecking outcomes/provenance, corruption, idempotency, missing evidence and checker failures.
- [x] Add migration 005 and registered checker/archive/sandbox/route modules; make tests pass.
- [x] Add the case-page rechecking control, result/evidence comparison and meaningful helper tests; typecheck and build.
- [x] Verify the real U05 archive in an independent check, preserving its hashes; test API and UI; run final review and address findings.
- [x] Document supported scope and verification results; deliver the visible platform link in plain Chinese.

## Decisions

- User approval of the preceding concrete design is implementation authorization; do not ask them to approve the same scope again.
- Native inline execution; a bounded independent final review will inspect only this change against the baseline.
- Rechecking is an offline product check, not a new Agent evaluation or evidence of capability improvement.

## Verification

- Final backend suite: 61 passed, 1 skipped (existing Windows symlink permission test); frontend: 17 passed; TypeScript and production build passed.
- Real native MXC controls: old U05 delivery fails behavior checks, reference fix passes behavior checks, syntax-broken delivery fails behavior checks while checking completes. All are independent checks, not new Agent runs.
- Actual platform UI: associated checker and completed one new real U05 saved-delivery check, expanded its evidence. New model requests0; original Agent30 requests, full archive242 requests and18/2 acceptance unchanged.
- Independent review issues fixed with red/green tests: zero/unrelated/filtered/skipped self-tests, missing empty protected files, delivery errors vs infrastructure, concurrent idempotency, stale-source history readability and polling recovery.
- Ruling: temporary execution copies use system temp to avoid Windows deep-path errors; persisted reports remain under data/check-runs. Existing dirty files unrelated to this feature remain byte-identical.
- No commit, push, Harness edit or task-data modification. Delivery receipts/screenshots are under this chat's outputs directory.
