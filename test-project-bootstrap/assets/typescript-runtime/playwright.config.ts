import { createRequire } from 'node:module';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveUiScriptScope } from './run-scope.mjs';

const require = createRequire(import.meta.url);
const { defineConfig } = require('@playwright/test');

const uiScope = resolveUiScriptScope(dirname(fileURLToPath(import.meta.url)), process.env);

export default defineConfig({
  testDir: uiScope.testDir,
  testMatch: uiScope.testMatch,
  fullyParallel: false,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: `${uiScope.resultsDir}/playwright-report.json` }]],
  outputDir: `${uiScope.resultsDir}/playwright-artifacts`,
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: process.env.TEST_RECORDING === 'true' ? 'on' : 'off',
  },
});
