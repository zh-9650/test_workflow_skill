import { resolve } from 'node:path';

export type RuntimeContext = {
  runDir: string;
  batchId: string;
  caseId: string;
  scriptTarget: string;
  attemptId: string;
  taskId: string;
  taskHash: string;
  workerSessionId: string;
  apiBaseUrl?: string;
  webBaseUrl?: string;
};

export function runtimeContext(env: NodeJS.ProcessEnv = process.env): RuntimeContext {
  if (!env.TEST_RUN_DIR || !env.TEST_BATCH_ID || !env.TEST_CASE_ID || !env.TEST_SCRIPT_TARGET || !env.TEST_ATTEMPT_ID
    || !env.TEST_TASK_ID || !env.TEST_TASK_HASH || !env.TEST_WORKER_SESSION_ID) {
    throw new Error('Run, Batch, Case, script, attempt, Task ID/hash, and Worker session scope are required');
  }
  const scriptTarget = env.TEST_SCRIPT_TARGET.replaceAll('\\', '/');
  const safeBatchId = /^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(env.TEST_BATCH_ID);
  const safeCaseId = /^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(env.TEST_CASE_ID);
  const safeAttemptId = /^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(env.TEST_ATTEMPT_ID);
  const parts = scriptTarget.split('/');
  const isApiTarget = parts.length === 4 && parts[0] === 'scripts' && parts[1] === 'api'
    && parts[2] === env.TEST_BATCH_ID && parts[3].endsWith('.test.ts');
  const isUiTarget = parts.length === 4 && parts[0] === 'scripts' && parts[1] === 'ui'
    && parts[2] === env.TEST_BATCH_ID && parts[3].endsWith('.spec.ts');
  const apiBaseUrl = env.TEST_API_BASE_URL?.trim();
  if (isApiTarget) {
    if (!apiBaseUrl) throw new Error('TEST_API_BASE_URL must come from the current Run execution context');
    let parsed: URL;
    try { parsed = new URL(apiBaseUrl); } catch { throw new Error('TEST_API_BASE_URL must be an absolute HTTP(S) URL'); }
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash) {
      throw new Error('TEST_API_BASE_URL must be an HTTP(S) base URL without credentials, query, or fragment');
    }
  }
  if (!safeBatchId || !safeCaseId || !safeAttemptId || (!isApiTarget && !isUiTarget)) {
    throw new Error('TEST_SCRIPT_TARGET and TEST_ATTEMPT_ID must be safe identifiers bound to the current Batch');
  }
  return {
    runDir: resolve(env.TEST_RUN_DIR),
    batchId: env.TEST_BATCH_ID,
    caseId: env.TEST_CASE_ID,
    scriptTarget,
    attemptId: env.TEST_ATTEMPT_ID,
    taskId: env.TEST_TASK_ID,
    taskHash: env.TEST_TASK_HASH,
    workerSessionId: env.TEST_WORKER_SESSION_ID,
    apiBaseUrl,
    webBaseUrl: env.TEST_WEB_BASE_URL,
  };
}
