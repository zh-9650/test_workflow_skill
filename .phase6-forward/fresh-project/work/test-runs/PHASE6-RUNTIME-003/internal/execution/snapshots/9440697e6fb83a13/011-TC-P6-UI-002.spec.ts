import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { expect, test } from '../../../../../test-automation/framework/playwright.js';
import { runtimeContext } from '../../../../../test-automation/framework/runtime-context.js';

const context = runtimeContext();
const caseDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-UI-002');

test('TC-P6-UI-002 checks heading before click and captures final result', async ({ page }) => {
  if (!context.webBaseUrl) throw new Error('TEST_WEB_BASE_URL is required');

  await page.goto(context.webBaseUrl);

  const heading = page.getByRole('heading', { name: 'Item lookup', exact: true });
  await expect(heading).toBeVisible();
  const uiDir = join(caseDir, 'ui');
  await mkdir(uiDir, { recursive: true });
  await page.screenshot({ path: join(uiDir, 'ASSERT-P6-UI-002-HEADING.png'), fullPage: true });

  await page.getByRole('button', { name: 'Load item', exact: true }).click();
  const result = page.locator('#result');
  await expect(result).toHaveText('Smoke item — ready');
  await page.screenshot({ path: join(uiDir, 'ASSERT-P6-UI-002-RESULT.png'), fullPage: true });
});
