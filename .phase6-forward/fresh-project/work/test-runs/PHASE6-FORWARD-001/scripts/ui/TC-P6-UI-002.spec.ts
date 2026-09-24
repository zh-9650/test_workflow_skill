import { join } from 'node:path';
import { mkdir } from 'node:fs/promises';
import { expect, test } from '../../../../test-automation/framework/playwright.js';
import { runtimeContext } from '../../../../test-automation/framework/runtime-context.js';

test('TC-P6-UI-002 critical item load shows the persisted key result', async ({ page }) => {
  const context = runtimeContext();
  const baseUrl = context.webBaseUrl;
  if (!baseUrl) throw new Error('TEST_WEB_BASE_URL is required');

  await page.goto(baseUrl);
  await expect(page.getByRole('heading', { name: 'Item lookup' })).toBeVisible();
  await page.getByRole('button', { name: 'Load item' }).click();
  const result = page.locator('#result');
  await expect(result).toHaveText('Smoke item — ready');
  await expect(result).toBeVisible();

  const evidenceDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-UI-002');
  await mkdir(evidenceDir, { recursive: true });
  await page.screenshot({ path: join(evidenceDir, 'critical-key-result.png'), fullPage: true });
});
