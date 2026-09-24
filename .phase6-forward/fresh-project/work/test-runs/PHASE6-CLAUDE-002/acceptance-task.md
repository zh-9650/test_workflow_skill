# PHASE6-CLAUDE-002 — Fresh Claude forward-acceptance task

Project: `.phase6-forward/fresh-project`  
Fixture only: `http://127.0.0.1:41739`  
Batch: `B01`

## Frozen Cases

| Case | Execution | Expected | Required evidence |
| --- | --- | --- | --- |
| `TC-P6-API-001` | TypeScript + Vitest + Node native `fetch` | `GET /api/items/1` returns HTTP 200 and exact JSON `{ "id": "1", "name": "Smoke item", "status": "ready" }`; `id` is a string. | Redacted request/response JSON and Vitest JSON report. |
| `TC-P6-UI-001` | TypeScript + Playwright Test | Click `Load item`; visible `#result` equals `Smoke item — ready`. | Result screenshot and Playwright JSON report. |
| `TC-P6-UI-002` | TypeScript + Playwright Test (critical) | Before click, heading `Item lookup` is visible; after click, visible `#result` equals `Smoke item — ready`. No persistence claim. | Distinct before/after screenshots, non-empty Playwright video and Playwright JSON report. |

## Role and execution protocol

The fresh Claude main session is the orchestrator only. It must read the Project Testing Index, this task, project `CLAUDE.md`, and both project agent definitions. It must create an independent `test-execution-worker` Agent to write each formal script before any Case execution, execute the three exact Cases using the required stacks, retain official reports/evidence, and complete Worker self-review. Only after that Agent completes, the main session must create a new independent `test-result-reviewer` Agent to inspect frozen scripts, reports, results and evidence without rerunning the Batch.

The Worker and Reviewer must be distinct actual Claude Agent tool calls/identities. Do not impersonate either role, do not invent IDs/receipts, and do not count a prose claim, JSON identity field, or runner exit code as proof of dispatch or Case PASS. Preserve the primary session's real Agent tool-use/tool-result trace as acceptance evidence. Each role returns its actual identity to the main session.

## Scope

Allowed writes are strictly below this Run directory: `scripts/`, `evidence/`, `runner-results/`, and Worker/Reviewer/final ledger outputs. The fixture is read-only and must only be accessed at `127.0.0.1:41739`. Do not modify fixture files, Bootstrap output, repository Skills/Contracts, global Skill installation, or any real business project. Do not alter PHASE6-RUNTIME-003 or PHASE6-CLAUDE-001.
