import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '../test-runs',
  testMatch: '**/scripts/ui/**/*.spec.ts',
  fullyParallel: false,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: 'test-results/playwright-report.json' }]],
  outputDir: 'test-results/playwright-artifacts',
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
