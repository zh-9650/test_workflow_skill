import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from 'vitest';

const caseId = 'TC-API-CREATE-RECOVER';
const dependencyId = 'TC-API-CREATE-VALID';
const runDirectory = resolve(
  process.env.TEST_RUN_DIR ?? resolve(process.cwd(), '../test-runs/PHASE5-RUN-002'),
);
const taskPath = resolve(runDirectory, 'internal/execution/tasks/B03-task.json');
const gateEvidencePath = resolve(
  runDirectory,
  'evidence/B03/TC-API-CREATE-RECOVER/gate/blocked-dependency.json',
);

test(`${caseId}: block without target request while B01 is reviewer-confirmed FAIL`, async () => {
  const task = JSON.parse(await readFile(taskPath, 'utf8')) as {
    task_id: string;
    task_hash: string;
    dependency_context: Record<
      string,
      { batch_id: string; status: string; final_result: string; reviewer_confirmed: boolean }
    >;
  };
  const dependency = task.dependency_context[dependencyId];

  expect(task.task_id).toBe('B03-903a8fd8784e');
  expect(task.task_hash).toBe('c4b4a6bc5e70c7b1efeec1cc0ccaf92c676309d1ce08c0454ae44c7833978833');
  expect(dependency).toMatchObject({
    batch_id: 'B01',
    status: 'FAIL',
    final_result: 'FAIL',
    reviewer_confirmed: true,
  });

  const evidence = {
    evidence_type: 'blocked_dependency',
    case_id: caseId,
    blocked_reason_type: 'upstream_case',
    affected_by: [dependencyId],
    target_action_executed: false,
    request_made: false,
    dependency_results: [
      {
        case_id: dependencyId,
        status: dependency.final_result,
        reviewer_confirmed: dependency.reviewer_confirmed,
      },
    ],
  };
  await mkdir(resolve(gateEvidencePath, '..'), { recursive: true });
  await writeFile(gateEvidencePath, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');

  // Deliberately no fetch/client import: an unresolved upstream gate permits no target request.
  expect(evidence.request_made).toBe(false);
  expect(evidence.dependency_results).toHaveLength(1);
});
