import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { expect, test } from '../../../../test-automation/framework/playwright.js';
import { runtimeContext } from '../../../../test-automation/framework/runtime-context.js';

const FIXTURE_BASE_URL = 'http://127.0.0.1:41739';

// Explicitly enable video recording for this critical case; the produced
// video file is copied to evidence/ after the formal run and must be non-empty.
test.use({ video: 'on' });

test('TC-P6-UI-002 heading visible before click and ready result after click', async ({ page }) => {
  const context = runtimeContext();

  await page.goto(FIXTURE_BASE_URL);

  // Before click: heading is visible.
  const heading = page.getByRole('heading', { name: 'Item lookup' });
  await expect(heading).toBeVisible();

  const evidenceDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-UI-002');
  await mkdir(evidenceDir, { recursive: true });
  await page.screenshot({ path: join(evidenceDir, 'before-click.png'), fullPage: true });

  // After click: result equals Smoke item — ready.
  await page.getByRole('button', { name: 'Load item' }).click();
  const result = page.locator('#result');
  await expect(result).toBeVisible();
  await expect(result).toHaveText('Smoke item — ready');
  await page.screenshot({ path: join(evidenceDir, 'after-click.png'), fullPage: true });
});
