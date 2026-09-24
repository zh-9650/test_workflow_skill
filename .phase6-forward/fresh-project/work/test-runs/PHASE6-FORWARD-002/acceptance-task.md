# PHASE6-FORWARD-002 — Frozen B01 acceptance task

Project: `.phase6-forward/fresh-project`  
Fixture only: `http://127.0.0.1:41739`  
Batch: `B01`

## Cases and exact Expected

| Case | Execution | Expected | Required evidence |
| --- | --- | --- | --- |
| `TC-P6-API-001` | TypeScript + Vitest + Node native `fetch` | `GET /api/items/1` returns HTTP 200 and the exact JSON object `{ "id": "1", "name": "Smoke item", "status": "ready" }`; `id` is a string. | Redacted request/response JSON under this Run and Vitest JSON report. |
| `TC-P6-UI-001` | TypeScript + Playwright Test | Click `Load item`; visible `#result` equals `Smoke item — ready`. | Key-result screenshot under this Run and Playwright JSON report. |
| `TC-P6-UI-002` | TypeScript + Playwright Test (critical) | Heading `Item lookup` visible; click `Load item`; visible `#result` equals `Smoke item — ready`. No persistence claim is made. | Key-result screenshot and non-empty Playwright video under this Run and Playwright JSON report. |

All three final scripts must exist before the first Case execution. The Execution Worker must perform the formal runs and self-review, then stop. A new Result Reviewer must independently inspect the frozen scripts, runner reports, and evidence without rerunning the Cases.

Allowed writes: this Run's `scripts/`, `evidence/`, `runner-results/`, and Worker self-review. Do not modify the fixture, project Bootstrap output, repository Skill/Contract files, global Skill directories, or any business project.
