import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { defineConfig } = require('@playwright/test');

const resultsDir = process.env.TEST_RESULTS_DIR ?? 'test-results';

export default defineConfig({
  testDir: '../test-runs',
  testMatch: '**/scripts/ui/**/*.spec.ts',
  fullyParallel: false,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: `${resultsDir}/playwright-report.json` }]],
  outputDir: `${resultsDir}/playwright-artifacts`,
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: process.env.TEST_RECORDING === 'true' ? 'on' : 'off',
  },
});
