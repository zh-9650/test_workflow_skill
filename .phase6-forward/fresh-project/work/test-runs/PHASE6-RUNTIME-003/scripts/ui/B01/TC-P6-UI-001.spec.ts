import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { expect, test } from '../../../../../test-automation/framework/playwright.js';
import { runtimeContext } from '../../../../../test-automation/framework/runtime-context.js';

const context = runtimeContext();
const caseDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-UI-001');

test('TC-P6-UI-001 displays the frozen item result', async ({ page }) => {
  if (!context.webBaseUrl) throw new Error('TEST_WEB_BASE_URL is required');

  await page.goto(context.webBaseUrl);
  await page.getByRole('button', { name: 'Load item', exact: true }).click();

  const result = page.locator('#result');
  await expect(result).toHaveText('Smoke item — ready');

  const uiDir = join(caseDir, 'ui');
  await mkdir(uiDir, { recursive: true });
  await page.screenshot({ path: join(uiDir, 'ASSERT-P6-UI-RESULT-001.png'), fullPage: true });
});
