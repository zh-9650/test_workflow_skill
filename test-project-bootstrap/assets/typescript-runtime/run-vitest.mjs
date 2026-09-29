import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveApiScriptScope } from './run-scope.mjs';

const automationRoot = dirname(fileURLToPath(import.meta.url));
if (process.argv.length > 2) {
  throw new Error('Vitest runner arguments are fixed; use the planned script_target and scoped environment only');
}
resolveApiScriptScope(automationRoot, process.env, { prepareAttempt: true });
process.env.TEST_SCOPE_PREPARED = '1';
const cli = resolve(automationRoot, 'node_modules', 'vitest', 'vitest.mjs');
const result = spawnSync(process.execPath, [cli, 'run', '--config', resolve(automationRoot, 'vitest.config.ts')], {
  cwd: automationRoot,
  env: process.env,
  stdio: 'inherit',
});

if (result.error) throw result.error;
process.exit(result.status ?? 1);
