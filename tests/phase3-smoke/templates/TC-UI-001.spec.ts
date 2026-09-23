import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from '../../../../../../work/test-automation/framework/playwright.js';
import { runtimeContext } from '../../../../../../work/test-automation/framework/runtime-context.js';

test('TC-UI-001 loads an item and captures the critical assertion', async ({ page }) => {
  const context = runtimeContext();
  if (!context.webBaseUrl) throw new Error('TEST_WEB_BASE_URL is required');
  await page.goto(new URL('/', context.webBaseUrl).toString());
  await page.getByRole('button', { name: 'Load item' }).click();
  await expect(page.locator('#result')).toHaveText('Smoke item — ready');

  const evidenceDir = resolve(context.runDir, 'evidence');
  await mkdir(evidenceDir, { recursive: true });
  await page.screenshot({ path: resolve(evidenceDir, 'TC-UI-001-key-result.png'), fullPage: true });
});
