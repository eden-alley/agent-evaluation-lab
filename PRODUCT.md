# Agent Evaluation Lab

## Current product direction
The user works in an external Coding Agent. It consumes published built-in and business Skills on demand and produces datasets according to user needs. This inbound direction supersedes the old platform-launches-Codex design.

## Skill ownership
Skills are first-class product knowledge. Their methodology must be co-designed with the user; do not author production Skill instructions independently. The built-in dataset-design record has metadata only and is not available as a published Skill. The platform implements user-authored versions, publication, discovery and artifact provenance.

## Delivered architecture
Next.js/TypeScript + FastAPI + SQLite WAL; official MCP stdio bridge to the existing API. Shared strict contracts and services, no microservices or generic plugin runtime. Projects register the agent under test, not the external Coding Agent client.

## Workflow
User requirement → external Agent reads context and applicable published Skills → immutable dataset draft → external quality report + deterministic platform checks → human review → immutable dataset version. Dataset and Skill changes preserve earlier versions.

## Boundaries
No paid model calls, Harness modifications, platform-launched Coding Agent, actual evaluation worker or autonomous improvement loop. Existing evaluation/Trace/comparison examples remain marked and separate from real storage. Skill origin declarations do not prove actual adherence. Approval tools are not exposed through MCP; local HTTP remains a single-user trusted interface.

## Visual authority
Use the supplied Design System: neutral surfaces, compact tables, blue primary actions and clear evidence links. Functional UI is Chinese. Navigation now includes first-class built-in Skills, reflecting the user's updated requirements.
