import { spawnSync } from 'node:child_process';
import { delimiter, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveUiScriptScope } from './run-scope.mjs';

const automationRoot = dirname(fileURLToPath(import.meta.url));
if (process.argv.length > 2) {
  throw new Error('Playwright runner arguments are fixed; use the planned script_target and scoped environment only');
}
resolveUiScriptScope(automationRoot, process.env, { prepareAttempt: true });
process.env.TEST_SCOPE_PREPARED = '1';
const nodeModules = resolve(automationRoot, 'node_modules');
const nodePath = [nodeModules, process.env.NODE_PATH].filter(Boolean).join(delimiter);
const cli = resolve(nodeModules, '@playwright/test/cli.js');
const result = spawnSync(process.execPath, [cli, 'test', '--config', resolve(automationRoot, 'playwright.config.ts')], {
  cwd: automationRoot,
  env: { ...process.env, NODE_PATH: nodePath },
  stdio: 'inherit',
});

if (result.error) throw result.error;
process.exit(result.status ?? 1);
