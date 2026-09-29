import { defineConfig } from 'vitest/config';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveApiScriptScope } from './run-scope.mjs';

const automationDir = dirname(fileURLToPath(import.meta.url));
const apiScope = resolveApiScriptScope(automationDir, process.env);

export default defineConfig({
  test: {
    include: [apiScope.include],
    reporters: ['default', 'json'],
    outputFile: { json: `${apiScope.resultsDir}/vitest-report.json` },
    testTimeout: 30_000,
  },
});
