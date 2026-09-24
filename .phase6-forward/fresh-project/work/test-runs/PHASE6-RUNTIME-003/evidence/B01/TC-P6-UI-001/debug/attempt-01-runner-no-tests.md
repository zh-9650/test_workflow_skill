# Diagnostic attempt 01 — Playwright test discovery

- Case: `TC-P6-UI-001`
- Time window: `2026-09-23T14:03:43.3779927Z` to `2026-09-23T14:03:44.3355608Z`
- Command: `npm exec -- playwright test --config playwright.config.ts ../test-runs/PHASE6-RUNTIME-003/scripts/ui/B01/TC-P6-UI-001.spec.ts`
- Outcome: runner exit code `1`; Playwright reported `No tests found.`
- Script SHA-256 before/after: `f8f81656cf931f4012efce8ce6b41a8ea080e5edc5338a67564ac593c6db1e1b` (unchanged)
- Observe: no browser test was discovered or run; no Case assertion was evaluated.
- Follow-up observation: a non-executing `playwright test --list` resolved both target files but reported `Cannot find module '@playwright/test'` from their location under the separate `work/test-runs` tree.
- A later non-executing discovery invocation omitted the required `TEST_RUN_DIR` / `TEST_BATCH_ID` values and was rejected by the framework context guard; after supplying the Task environment, `--list` discovered exactly the single intended TC-P6-UI-001 test.
- Diagnosis: (1) the CLI file filter must be relative to the configured `testDir` (`PHASE6-RUNTIME-003/...`, not `../test-runs/PHASE6-RUNTIME-003/...`); (2) test files must import Playwright Test through the project framework wrapper so Node resolves the dependency from `work/test-automation/node_modules`.
- Action: update only the two planned UI script imports; rerun typecheck and the official Playwright runner. No Case/Expected/Plan changes.
