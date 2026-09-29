import { spawnSync } from 'node:child_process';
import { existsSync, lstatSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveApiScriptScope, resolveUiScriptScope } from './run-scope.mjs';

const automationRoot = dirname(fileURLToPath(import.meta.url));
if (process.argv.length > 2) throw new Error('Typecheck runner arguments are fixed; use the scoped environment only');

const driver = process.env.TEST_DRIVER ?? 'api';
const scope = driver === 'ui'
  ? resolveUiScriptScope(automationRoot, process.env, { validateOnly: true })
  : resolveApiScriptScope(automationRoot, process.env, { validateOnly: true });
const target = driver === 'ui' ? resolve(scope.testDir, scope.testMatch) : scope.absoluteTarget;
const frameworkRoot = resolve(automationRoot, 'framework');

function collectFrameworkSources(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Typecheck source cannot be a symbolic link: ${path}`);
    if (entry.isDirectory()) return collectFrameworkSources(path);
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

function isWithin(parent, child) {
  const path = relative(parent, child);
  return path === '' || (!path.startsWith(`..${sep}`) && path !== '..' && !isAbsolute(path));
}

if (!existsSync(target) || !isWithin(scope.runDir, target)) throw new Error('Scoped script target is missing or escapes the current Run');
const sourceFiles = [...collectFrameworkSources(frameworkRoot), target];
const temporaryDirectory = mkdtempSync(join(automationRoot, '.typecheck-temp-'));
const temporaryConfig = join(temporaryDirectory, 'tsconfig.json');
try {
  writeFileSync(temporaryConfig, JSON.stringify({
    extends: resolve(automationRoot, 'tsconfig.json'),
    files: [...new Set(sourceFiles)],
    include: [],
  }, null, 2), 'utf8');
  const compiler = resolve(automationRoot, 'node_modules/typescript/bin/tsc');
  if (!existsSync(compiler) || !lstatSync(compiler).isFile()) throw new Error('Pinned TypeScript compiler is unavailable');
  const result = spawnSync(process.execPath, [compiler, '--noEmit', '--project', temporaryConfig], {
    cwd: automationRoot,
    env: process.env,
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
  if (process.exitCode === 0) process.stdout.write(`Typecheck passed for ${scope.target}\n`);
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true });
}
