# Integrate task explanations into the lightweight analysis Skill

User approved: improve PR1 by replacing the standalone explanation Skill with guidance in the existing analysis Skill; persist and display selected case explanations; fix platform payload hashes. Validate the existing real U05 archive offline. No model/scorer/evaluation runs or original score changes.

## Design

- Optional explanations alongside the existing summary and recommendations. Cover selected cases, show coverage explicitly; do not require twenty long narratives.
- A case explanation names the A/B focus, task background, a small number of progress stages, observed result and limitations. Stages and result use friendly file/event/check references.
- The program resolves references against the pinned case catalog and freezes excerpts. Reject wrong cases, missing events/checks and mixed source focus before writing. Append case and final reports in the existing atomic transaction.
- Keep legacy input idempotency when the new optional list is absent or empty. Preserve older reports and deterministic metric definitions.
- Show task background and process first in case details, with evidence on demand. Keep original criteria, metrics and raw files accessible.
- Keep full examples/evidence as optional reference artifacts, outside the default platform Skill text. Normalize the actual API content before hashing and count the normalized characters.
- Start from main7d3c2ba, integrate PR head128c5918 on its local branch without changing main. Resolve catalog/README while retaining existing Skill entries. Keep the PR draft; do not merge it.

## Tasks

- [x] Add failing contract/reference/legacy-idempotency tests.
- [x] Implement optional explanation storage, friendly evidence resolution and coverage.
- [x] Integrate short explanation guidance and optional reference examples; verify actual API hash.
- [x] Implement case-first platform presentation and old-report fallback.
- [x] Verify API/MCP/CLI plus real U05, inspect the local platform and pin preservation evidence.
- [x] Prepare the integrated PR patch and revised title/body after a concrete local preview exists; publish to the existing draft PR without merging.

## Validation boundaries

Offline program fixtures and curated narrative text validate storage, references and presentation. They do not demonstrate a model followed the Skill or verify semantic/causal judgement. U05 is the formal20 CLI limits task, not the older Click prototype.

## Verification ledger

- 109 backend tests passed,1 Windows symlink test skipped;32 frontend tests passed;isolated production build passed. Actual MCP and CLI exercised without models or scorers.
- Live comparison12b854ab-67d0-41da-bf7d-7151548f37c7,report e22517df-739b-44a1-851d-0a9b7fc355b1. Existing Skill aafb49bf-c692-4f47-ab21-b3735f0d0421,version0f48f716-3791-4253-b45d-8c4b76e58b2a,method0.3.0,3382characters.
- Three B stages reference events41,51,61,66,70,114,118,121 plus saved checks. Real U05 CLI retry returned the same receipt; the old20-case request still returned70228db5-c312-4139-8677-778bc67c4aaa.
- All149 pinned U05/archive metadata files unchanged. Every preexisting comparison,case/final report,Skill version,judgment,check run andchecker binding row preserved. Only1 comparison,1 case report,1 final report and1 Skill version appended.
- Browser inspected task-first view and expanded event66/70 evidence. Screenshots and preservation receipt saved locally under outputs/U05讲解整合验证-20261113. No model calls,evaluation reruns,original grade changes or merge to main.
