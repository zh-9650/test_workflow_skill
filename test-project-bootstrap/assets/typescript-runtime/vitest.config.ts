import { defineConfig } from 'vitest/config';

const resultsDir = process.env.TEST_RESULTS_DIR ?? 'test-results';

export default defineConfig({
  test: {
    include: ['../test-runs/**/scripts/api/**/*.test.ts'],
    reporters: ['default', 'json'],
    outputFile: { json: `${resultsDir}/vitest-report.json` },
    testTimeout: 30_000,
  },
});
