import { createHash } from 'node:crypto';
import { existsSync, lstatSync, mkdirSync, readFileSync, realpathSync } from 'node:fs';
import { basename, dirname, isAbsolute, relative, resolve, sep } from 'node:path';

function fail(message) {
  throw new Error(`Automation execution scope rejected: ${message}`);
}

function isWithin(parent, child) {
  const path = relative(parent, child);
  return path === '' || (!path.startsWith(`..${sep}`) && path !== '..' && !isAbsolute(path));
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function canonicalSha256(value) {
  return createHash('sha256').update(canonicalJson(value), 'utf8').digest('hex');
}

function readSafeJson(runDir, relativePath, description) {
  if (typeof relativePath !== 'string' || !relativePath.trim()) fail(`${description} reference is required`);
  const normalized = relativePath.replaceAll('\\', '/');
  const parts = normalized.split('/');
  if (isAbsolute(normalized) || /^[A-Za-z]:/.test(normalized) || parts.some((part) => !part || part === '.' || part === '..')) {
    fail(`${description} reference must be a safe Run-relative path`);
  }
  let candidate = runDir;
  for (const [index, part] of parts.entries()) {
    candidate = resolve(candidate, part);
    if (!isWithin(runDir, candidate) || !existsSync(candidate) || lstatSync(candidate).isSymbolicLink()) {
      fail(`${description} path must exist inside the Run without symbolic links`);
    }
    const stat = lstatSync(candidate);
    if (index < parts.length - 1 ? !stat.isDirectory() : !stat.isFile()) {
      fail(`${description} path must contain real directories and a regular file`);
    }
  }
  const realPath = realpathSync(candidate);
  if (!isWithin(runDir, realPath)) fail(`${description} path resolves outside the Run`);
  try {
    return JSON.parse(readFileSync(realPath, 'utf8'));
  } catch {
    fail(`${description} must be readable JSON`);
  }
}

function resolveScriptTarget(automationDir, env, { driver, pattern, extension, prepareAttempt = false, validateOnly = false }) {
  for (const name of ['TEST_RUN_DIR', 'TEST_BATCH_ID', 'TEST_CASE_ID', 'TEST_SCRIPT_TARGET', 'TEST_RESULTS_DIR', 'TEST_TASK_ID', 'TEST_TASK_HASH', 'TEST_WORKER_SESSION_ID']) {
    if (!env[name]?.trim()) fail(`${name} is required; broad automation runs are forbidden`);
  }
  if (driver === 'api') {
    if (!env.TEST_API_BASE_URL?.trim()) fail('TEST_API_BASE_URL is required; API target defaults are forbidden');
    let apiBase;
    try { apiBase = new URL(env.TEST_API_BASE_URL); } catch { fail('TEST_API_BASE_URL must be a valid absolute URL'); }
    if (!['http:', 'https:'].includes(apiBase.protocol) || apiBase.username || apiBase.password || apiBase.search || apiBase.hash) {
      fail('TEST_API_BASE_URL must be an HTTP(S) base URL without credentials, query, or fragment');
    }
  }

  const automationRoot = realpathSync(resolve(automationDir));
  const testRunsRoot = realpathSync(resolve(automationRoot, '../test-runs'));
  const runDir = realpathSync(resolve(env.TEST_RUN_DIR));
  if (!isWithin(testRunsRoot, runDir) || relative(testRunsRoot, runDir).split(sep).length !== 1) {
    fail('TEST_RUN_DIR must be one direct Run directory under test-runs');
  }
  const runId = basename(runDir);
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(runId)) fail('Run directory name must be a glob-safe identifier');

  if (driver === 'api') {
    const context = readSafeJson(runDir, 'internal/execution/execution-context.yaml', 'API execution context');
    if (context?.environment_ready !== true || typeof context?.api_base_url !== 'string' || !context.api_base_url.trim()) {
      fail('API execution context must declare environment_ready=true and api_base_url');
    }
    let configuredBase;
    try { configuredBase = new URL(context.api_base_url); } catch { fail('API execution context api_base_url must be an absolute URL'); }
    const requestedBase = new URL(env.TEST_API_BASE_URL);
    if (configuredBase.href !== requestedBase.href) fail('TEST_API_BASE_URL must exactly match the current Run execution context');
  }

  const batchId = env.TEST_BATCH_ID;
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(batchId)) fail('TEST_BATCH_ID is invalid');
  const caseId = env.TEST_CASE_ID;
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(caseId)) fail('TEST_CASE_ID is invalid');
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(env.TEST_ATTEMPT_ID ?? '')) fail('TEST_ATTEMPT_ID must be a unique glob-safe identifier');

  const target = env.TEST_SCRIPT_TARGET.replaceAll('\\', '/');
  const targetMatch = pattern.exec(target);
  if (!targetMatch) fail(`TEST_SCRIPT_TARGET must identify one ${driver} ${extension} file in the current Run`);
  if (targetMatch[1] !== batchId) fail('TEST_SCRIPT_TARGET must be inside the current Batch');
  const scriptName = target.split('/').at(-1);
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]*\.(?:test|spec)\.ts$/.test(scriptName)) {
    fail('TEST_SCRIPT_TARGET basename must be glob-safe');
  }

  const scopedDirs = ['scripts', driver, batchId];
  let scopedPath = runDir;
  for (const part of scopedDirs) {
    scopedPath = resolve(scopedPath, part);
    if (!existsSync(scopedPath) || lstatSync(scopedPath).isSymbolicLink()) {
      fail('script path directories must exist and cannot be symbolic links');
    }
  }
  const absoluteTarget = resolve(runDir, ...target.split('/'));
  if (!isWithin(runDir, absoluteTarget) || !existsSync(absoluteTarget)) {
    fail('TEST_SCRIPT_TARGET must exist inside the current Run');
  }
  if (lstatSync(absoluteTarget).isSymbolicLink()) fail('TEST_SCRIPT_TARGET cannot be a symbolic link');
  const realTarget = realpathSync(absoluteTarget);
  if (!isWithin(runDir, realTarget) || relative(scopedPath, realTarget) !== basename(target)) {
    fail('TEST_SCRIPT_TARGET must resolve to this exact Case file inside the current Batch');
  }

  const runtimeState = readSafeJson(
    runDir,
    `internal/execution/runtime-state/${batchId}-state.json`,
    'Runtime state',
  );
  if (runtimeState?.batch_id !== batchId || !['running', 'retest_running'].includes(runtimeState?.status)) {
    fail('Runtime state must show this Batch actively running');
  }
  const active = runtimeState.active_retest ?? runtimeState;
  const taskRef = active.task_ref ?? runtimeState.task_ref;
  const taskRefParts = typeof taskRef === 'string' ? taskRef.replaceAll('\\', '/').split('/') : [];
  if (taskRefParts.length !== 4 || taskRefParts[0] !== 'internal' || taskRefParts[1] !== 'execution'
    || taskRefParts[2] !== 'tasks' || !taskRefParts[3].startsWith(`${batchId}-`)
    || !/^[A-Za-z0-9][A-Za-z0-9_-]*\.json$/.test(taskRefParts[3])) {
    fail('Runtime state must identify the active frozen Batch Task');
  }
  const task = readSafeJson(runDir, taskRef, 'Frozen Batch task');
  const { task_hash: taskHash, ...taskPayload } = task ?? {};
  if (!/^[a-f0-9]{64}$/.test(taskHash ?? '') || canonicalSha256(taskPayload) !== taskHash) {
    fail('the frozen Batch task task_hash does not match its canonical payload');
  }
  const workerReceipt = active.worker_dispatch_receipt;
  const dispatchReceipt = readSafeJson(runDir, active.worker_receipt_ref, 'Worker dispatch receipt');
  for (const key of ['agent_role', 'receipt_status', 'accepted_at', 'agent_session_id', 'task_id', 'task_hash', 'host_dispatch_ref', 'dispatch_source']) {
    if (!workerReceipt?.[key] || workerReceipt[key] !== dispatchReceipt?.[key]) {
      fail(`Runtime state and Worker dispatch receipt disagree on ${key}`);
    }
  }
  if (workerReceipt.agent_role !== 'execution_worker' || workerReceipt.receipt_status !== 'dispatched'
    || typeof workerReceipt.accepted_at !== 'string' || !workerReceipt.accepted_at.trim()
    || workerReceipt.agent_session_id !== env.TEST_WORKER_SESSION_ID
    || workerReceipt.task_id !== env.TEST_TASK_ID || workerReceipt.task_hash !== env.TEST_TASK_HASH
    || workerReceipt.task_id !== task?.task_id || workerReceipt.task_hash !== taskHash
    || !['codex_subagent_tool', 'claude_task_tool'].includes(workerReceipt.dispatch_source)) {
    fail('Worker dispatch receipt does not anchor the active frozen Batch Task');
  }
  if (active.current_case !== caseId || active.current_worker !== workerReceipt.agent_session_id) {
    fail('TEST_CASE_ID and dispatched Worker must match the active Runtime Case');
  }
  if (task?.batch_id !== batchId || !Array.isArray(task.cases)) fail('the frozen Batch task does not match TEST_BATCH_ID');
  if (task.task_id !== env.TEST_TASK_ID || task.task_hash !== env.TEST_TASK_HASH) {
    fail('active task_id/task_hash must match the worker receipt and invocation environment');
  }
  const caseMatches = task.cases.filter((item) => item?.case_id === caseId);
  if (caseMatches.length !== 1 || caseMatches[0]?.automation?.script_target?.replaceAll('\\', '/') !== target) {
    fail('TEST_CASE_ID and TEST_SCRIPT_TARGET must match exactly one Case in the frozen Batch task');
  }
  const resultsDir = resolve(runDir, 'runner-results', batchId, caseId, env.TEST_ATTEMPT_ID);
  if (relative(resultsDir, resolve(env.TEST_RESULTS_DIR)) !== '') {
    fail('TEST_RESULTS_DIR must be the dedicated runner-results/<Batch>/<Case>/<Attempt> directory');
  }
  let resultPath = runDir;
  for (const part of ['runner-results', batchId, caseId, env.TEST_ATTEMPT_ID]) {
    resultPath = resolve(resultPath, part);
    if (existsSync(resultPath) && (lstatSync(resultPath).isSymbolicLink() || !lstatSync(resultPath).isDirectory())) {
      fail('TEST_RESULTS_DIR path cannot contain symbolic links or non-directory components');
    }
  }
  if (prepareAttempt) {
    if (existsSync(resultsDir)) fail('TEST_ATTEMPT_ID already has output; allocate a new attempt and never overwrite evidence');
    mkdirSync(dirname(resultsDir), { recursive: true });
    mkdirSync(resultsDir);
  } else if (!validateOnly && (!existsSync(resultsDir) || env.TEST_SCOPE_PREPARED !== '1')) {
    fail('official runner must prepare a new TEST_ATTEMPT_ID before loading its config');
  }
  if (!validateOnly && realpathSync(resultsDir) !== resultsDir) fail('TEST_RESULTS_DIR must resolve to its dedicated Run/Batch/Case path');

  return {
    runDir,
    target,
    absoluteTarget: realTarget,
    include: `../test-runs/${relative(testRunsRoot, runDir).split(sep).join('/')}/${target}`,
    resultsDir,
  };
}

export function resolveApiScriptScope(automationDir, env = process.env, options = {}) {
  return resolveScriptTarget(automationDir, env, {
    driver: 'api',
    pattern: /^scripts\/api\/([^/]+)\/([^/]+\.test\.ts)$/,
    extension: 'test.ts',
    ...options,
  });
}

export function resolveUiScriptScope(automationDir, env = process.env, options = {}) {
  const { runDir, target, resultsDir } = resolveScriptTarget(automationDir, env, {
    driver: 'ui',
    pattern: /^scripts\/ui\/([^/]+)\/([^/]+\.spec\.ts)$/,
    extension: 'spec.ts',
    ...options,
  });
  return {
    testDir: dirname(resolve(runDir, ...target.split('/'))),
    testMatch: target.split('/').at(-1),
    resultsDir,
  };
}
