# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: PHASE6-RUNTIME-003\scripts\ui\B01\TC-P6-UI-002.spec.ts >> TC-P6-UI-002 checks heading before click and captures final result
- Location: ..\test-runs\PHASE6-RUNTIME-003\scripts\ui\B01\TC-P6-UI-002.spec.ts:17:5

# Error details

```
Test timeout of 30000ms exceeded while running "afterEach" hook.
```

# Page snapshot

```yaml
- main [ref=e2]:
  - heading "Item lookup" [level=1] [ref=e3]
  - button "Load item" [active] [ref=e4]
  - status [ref=e5]: Smoke item — ready
```

# Test source

```ts
  1  | import { mkdir } from 'node:fs/promises';
  2  | import { join } from 'node:path';
  3  | import { expect, test } from '../../../../../test-automation/framework/playwright.js';
  4  | import { runtimeContext } from '../../../../../test-automation/framework/runtime-context.js';
  5  | 
  6  | const context = runtimeContext();
  7  | const caseDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-UI-002');
  8  | 
> 9  | test.afterEach(async ({ page }) => {
     |      ^ Test timeout of 30000ms exceeded while running "afterEach" hook.
  10 |   const video = page.video();
  11 |   if (!video) return;
  12 |   const uiDir = join(caseDir, 'ui');
  13 |   await mkdir(uiDir, { recursive: true });
  14 |   await video.saveAs(join(uiDir, 'TC-P6-UI-002.webm'));
  15 | });
  16 | 
  17 | test('TC-P6-UI-002 checks heading before click and captures final result', async ({ page }) => {
  18 |   if (!context.webBaseUrl) throw new Error('TEST_WEB_BASE_URL is required');
  19 | 
  20 |   await page.goto(context.webBaseUrl);
  21 | 
  22 |   const heading = page.getByRole('heading', { name: 'Item lookup', exact: true });
  23 |   await expect(heading).toBeVisible();
  24 |   const uiDir = join(caseDir, 'ui');
  25 |   await mkdir(uiDir, { recursive: true });
  26 |   await page.screenshot({ path: join(uiDir, 'ASSERT-P6-UI-002-HEADING.png'), fullPage: true });
  27 | 
  28 |   await page.getByRole('button', { name: 'Load item', exact: true }).click();
  29 |   const result = page.locator('#result');
  30 |   await expect(result).toHaveText('Smoke item — ready');
  31 |   await page.screenshot({ path: join(uiDir, 'ASSERT-P6-UI-002-RESULT.png'), fullPage: true });
  32 | });
  33 | 
```