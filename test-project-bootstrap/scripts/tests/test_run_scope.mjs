import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { test } from 'node:test';
import { resolveApiScriptScope } from '../../assets/typescript-runtime/run-scope.mjs';

const caseId = 'TC-API-CREATE-VALID';
const target = `scripts/api/B01/${caseId}.test.ts`;

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function hash(value) {
  return createHash('sha256').update(canonical(value), 'utf8').digest('hex');
}

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'test-run-scope-'));
  const automationDir = resolve(root, 'work/test-automation');
  const runDir = resolve(root, 'work/test-runs/PHASE5-SCOPE-001');
  const taskRef = 'internal/execution/tasks/B01-task.json';
  const receiptRef = 'internal/execution/dispatch/B01-worker-receipt.json';
  const scriptPath = resolve(runDir, ...target.split('/'));
  mkdirSync(automationDir, { recursive: true });
  mkdirSync(resolve(runDir, 'scripts/api/B01'), { recursive: true });
  mkdirSync(resolve(runDir, 'internal/execution/tasks'), { recursive: true });
  mkdirSync(resolve(runDir, 'internal/execution/dispatch'), { recursive: true });
  writeFileSync(resolve(runDir, 'internal/execution/execution-context.yaml'), JSON.stringify({
    environment_ready: true,
    api_base_url: 'http://127.0.0.1:44174',
  }));
  writeFileSync(scriptPath, '// isolated scope fixture; never executed\n');

  const task = {
    schema_version: 2,
    workflow_version: '2.0.0',
    task_id: 'B01-scope-fixture',
    batch_id: 'B01',
    case_order: [caseId],
    cases: [{ case_id: caseId, automation: { script_target: target } }],
  };
  task.task_hash = hash(task);
  writeFileSync(resolve(runDir, taskRef), `${JSON.stringify(task, null, 2)}\n`);

  const receipt = {
    agent_role: 'execution_worker',
    agent_session_id: 'synthetic-unit-fixture-worker',
    task_id: task.task_id,
    task_hash: task.task_hash,
    dispatch_source: 'codex_subagent_tool',
    host_dispatch_ref: 'synthetic-unit-fixture-dispatch',
    accepted_at: '2026-09-24T00:00:00Z',
    receipt_status: 'dispatched',
  };
  writeFileSync(resolve(runDir, receiptRef), `${JSON.stringify(receipt, null, 2)}\n`);
  const runtimeState = {
    batch_id: 'B01',
    status: 'running',
    task_ref: taskRef,
    current_case: caseId,
    current_worker: receipt.agent_session_id,
    worker_dispatch_receipt: receipt,
    worker_receipt_ref: receiptRef,
  };
  mkdirSync(resolve(runDir, 'internal/execution/runtime-state'), { recursive: true });
  writeFileSync(resolve(runDir, 'internal/execution/runtime-state/B01-state.json'), `${JSON.stringify(runtimeState, null, 2)}\n`);

  return { root, automationDir, runDir, task, taskPath: resolve(runDir, taskRef), scriptPath };
}

function envFor(f, attemptId) {
  return {
    TEST_RUN_DIR: f.runDir,
    TEST_BATCH_ID: 'B01',
    TEST_CASE_ID: caseId,
    TEST_SCRIPT_TARGET: target,
    TEST_ATTEMPT_ID: attemptId,
    TEST_RESULTS_DIR: resolve(f.runDir, 'runner-results/B01', caseId, attemptId),
    TEST_TASK_ID: f.task.task_id,
    TEST_TASK_HASH: f.task.task_hash,
    TEST_WORKER_SESSION_ID: 'synthetic-unit-fixture-worker',
    TEST_API_BASE_URL: 'http://127.0.0.1:44174',
  };
}

test('accepts only the active Case anchored to the dispatched Task and receipt', () => {
  const f = fixture();
  try {
    const scope = resolveApiScriptScope(f.automationDir, envFor(f, 'ATTEMPT-001'), { prepareAttempt: true });
    assert.equal(scope.target, target);
    assert.equal(scope.runDir, f.runDir);
    assert.equal(existsSync(resolve(f.runDir, 'runner-results/B01', caseId, 'ATTEMPT-001')), true);
  } finally {
    rmSync(f.root, { recursive: true, force: true });
  }
});

test('rejects a Task whose payload and embedded hash changed after host dispatch', () => {
  const f = fixture();
  try {
    const task = JSON.parse(readFileSync(f.taskPath, 'utf8'));
    task.cases[0].automation.script_target = 'scripts/api/B01/TC-API-OTHER.test.ts';
    delete task.task_hash;
    task.task_hash = hash(task);
    writeFileSync(f.taskPath, `${JSON.stringify(task, null, 2)}\n`);
    assert.throws(
      () => resolveApiScriptScope(f.automationDir, envFor(f, 'ATTEMPT-002'), { prepareAttempt: true }),
      /Worker dispatch receipt does not anchor the active frozen Batch Task/,
    );
    assert.equal(existsSync(resolve(f.runDir, 'runner-results/B01', caseId, 'ATTEMPT-002')), false);
  } finally {
    rmSync(f.root, { recursive: true, force: true });
  }
});

test('rejects API scope without an explicit Run-derived base URL', () => {
  const f = fixture();
  try {
    const env = envFor(f, 'ATTEMPT-003');
    delete env.TEST_API_BASE_URL;
    assert.throws(
      () => resolveApiScriptScope(f.automationDir, env, { prepareAttempt: true }),
      /TEST_API_BASE_URL is required/,
    );
    assert.equal(existsSync(resolve(f.runDir, 'runner-results/B01', caseId, 'ATTEMPT-003')), false);
  } finally {
    rmSync(f.root, { recursive: true, force: true });
  }
});

test('rejects API base URL that differs from the current Run context before preparing an Attempt', () => {
  const f = fixture();
  try {
    const env = envFor(f, 'ATTEMPT-004');
    env.TEST_API_BASE_URL = 'http://127.0.0.1:4174';
    assert.throws(
      () => resolveApiScriptScope(f.automationDir, env, { prepareAttempt: true }),
      /must exactly match the current Run execution context/,
    );
    assert.equal(existsSync(resolve(f.runDir, 'runner-results/B01', caseId, 'ATTEMPT-004')), false);
  } finally {
    rmSync(f.root, { recursive: true, force: true });
  }
});
