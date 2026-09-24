# Diagnostic attempt 01 — critical UI recording finalization

- Case: `TC-P6-UI-002`
- Runner: Playwright Test; configured `TEST_RECORDING=true`.
- Observation: both planned screenshots were emitted: `ASSERT-P6-UI-002-HEADING.png` before the click and `ASSERT-P6-UI-002-RESULT.png` after it. The runner report shows the test timed out in the `afterEach` hook at 30 seconds while calling `video.saveAs`; Playwright did not finish the test, so this attempt is not an accepted Case result.
- Preserved evidence: this directory contains the raw failed `playwright-report.json`, failure screenshot, error-context, and trace ZIP from the attempt.
- Diagnosis: `video.saveAs` waits for video finalization, which occurs when the browser context closes; awaiting it from `afterEach` deadlocks within Playwright's test timeout.
- Action: remove the `afterEach` save call. Keep video enabled through Playwright Test's configured `video: 'on'`; after the official runner fully exits, copy its finalized video attachment into this Case's `ui/` evidence directory. No Case/Expected/Plan changes.
