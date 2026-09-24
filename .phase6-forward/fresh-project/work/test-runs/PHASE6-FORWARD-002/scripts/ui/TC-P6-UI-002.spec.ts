import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { expect, test } from '../../../../test-automation/framework/playwright.js';
import { runtimeContext } from '../../../../test-automation/framework/runtime-context.js';

test('TC-P6-UI-002 critical lookup shows the ready item', async ({ page }) => {
  const context = runtimeContext();
  if (!context.webBaseUrl) throw new Error('TEST_WEB_BASE_URL is required');

  await page.goto(context.webBaseUrl);
  await expect(page.getByRole('heading', { name: 'Item lookup' })).toBeVisible();
  await page.getByRole('button', { name: 'Load item' }).click();
  const result = page.locator('#result');
  await expect(result).toBeVisible();
  await expect(result).toHaveText('Smoke item — ready');

  const evidenceDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-UI-002');
  await mkdir(evidenceDir, { recursive: true });
  await page.screenshot({ path: join(evidenceDir, 'critical-key-result.png'), fullPage: true });
});
