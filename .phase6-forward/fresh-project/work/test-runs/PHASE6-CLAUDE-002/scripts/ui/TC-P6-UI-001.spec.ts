import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { expect, test } from '../../../../test-automation/framework/playwright.js';
import { runtimeContext } from '../../../../test-automation/framework/runtime-context.js';

const FIXTURE_BASE_URL = 'http://127.0.0.1:41739';

test('TC-P6-UI-001 clicking Load item shows Smoke item — ready', async ({ page }) => {
  const context = runtimeContext();

  await page.goto(FIXTURE_BASE_URL);

  const result = page.locator('#result');
  await expect(result).toBeVisible();

  await page.getByRole('button', { name: 'Load item' }).click();

  await expect(result).toBeVisible();
  await expect(result).toHaveText('Smoke item — ready');

  const evidenceDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-UI-001');
  await mkdir(evidenceDir, { recursive: true });
  await page.screenshot({ path: join(evidenceDir, 'result.png'), fullPage: true });
});
