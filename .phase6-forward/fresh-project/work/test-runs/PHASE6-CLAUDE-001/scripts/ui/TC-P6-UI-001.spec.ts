import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { expect, test } from '../../../../test-automation/framework/playwright.js';
import { runtimeContext } from '../../../../test-automation/framework/runtime-context.js';

test('TC-P6-UI-001 loads item and shows ready result', async ({ page }) => {
  const context = runtimeContext();
  if (!context.webBaseUrl) throw new Error('TEST_WEB_BASE_URL is required');

  await page.goto(context.webBaseUrl);
  await page.getByRole('button', { name: 'Load item' }).click();
  const result = page.locator('#result');
  await expect(result).toBeVisible();
  await expect(result).toHaveText('Smoke item — ready');

  const evidenceDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-UI-001');
  await mkdir(evidenceDir, { recursive: true });
  await page.screenshot({ path: join(evidenceDir, 'key-result.png'), fullPage: true });
});
