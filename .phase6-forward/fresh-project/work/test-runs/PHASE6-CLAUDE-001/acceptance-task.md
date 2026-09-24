# PHASE6-CLAUDE-001 — Frozen B01 Claude forward-acceptance task

Project: `.phase6-forward/fresh-project`  
Fixture only: `http://127.0.0.1:41739`  
Batch: `B01`

## Cases and exact Expected

| Case | Execution | Expected | Required evidence |
| --- | --- | --- | --- |
| `TC-P6-API-001` | TypeScript + Vitest + Node native `fetch` | `GET /api/items/1` returns HTTP 200 and exact JSON `{ "id": "1", "name": "Smoke item", "status": "ready" }`; `id` is a string. | Redacted request/response JSON and Vitest JSON report. |
| `TC-P6-UI-001` | TypeScript + Playwright Test | Click `Load item`; visible `#result` equals `Smoke item — ready`. | Key-result screenshot and Playwright JSON report. |
| `TC-P6-UI-002` | TypeScript + Playwright Test (critical) | Heading `Item lookup` visible; click `Load item`; visible `#result` equals `Smoke item — ready`. No persistence claim is made. | Key-result screenshot, non-empty Playwright video and Playwright JSON report. |

All Case scripts must be written before the first Case execution. The main Claude Agent must dispatch the project-defined independent Execution Worker, wait for its formal runs and self-review, then dispatch a new independent Result Reviewer. The Reviewer must inspect frozen scripts, reports and evidence without rerunning the Batch. Do not self-perform either delegated role, invent receipts/session IDs, or treat runner exit status as Case verdict.

Allowed writes: this Run's `scripts/`, `evidence/`, `runner-results/`, execution records, and role review notes. Do not modify the fixture, Bootstrap output, repository Skills/Contracts, global Skill installation, or any real business project.
