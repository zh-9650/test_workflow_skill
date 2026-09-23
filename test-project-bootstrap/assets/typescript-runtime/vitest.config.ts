import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['../test-runs/**/scripts/api/**/*.test.ts'],
    reporters: ['default', 'json'],
    outputFile: { json: 'test-results/vitest-report.json' },
    testTimeout: 30_000,
  },
});
