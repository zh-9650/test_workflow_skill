import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { saveJsonEvidence } from '../../../../../test-automation/framework/evidence.js';
import { request } from '../../../../../test-automation/framework/api-client.js';

const caseId = 'TC-API-READ-ISOLATED';
const expectedId = 'A-TC-API-READ-ISOLATED';
const runDirectory = resolve(
  process.env.TEST_RUN_DIR ?? resolve(process.cwd(), '../test-runs/PHASE5-RUN-002'),
);
const evidencePath = resolve(
  runDirectory,
  'evidence/B02/TC-API-READ-ISOLATED/api/read-request-response.json',
);

test(`${caseId}: read immutable control item`, async () => {
  const baseUrl = process.env.PHASE5_API_BASE_URL ?? 'http://127.0.0.1:4174';
  const response = await request({
    method: 'GET',
    url: `${baseUrl}/api/items/control-001`,
    timeoutMs: 5_000,
  });

  // The shared API client supplies the redacted:true request/response evidence.
  await saveJsonEvidence(evidencePath, {
    ...response.evidence,
    case_id: caseId,
    expected_id: expectedId,
  });

  expect(response.method).toBe('GET');
  expect(response.url).toBe(`${baseUrl}/api/items/control-001`);
  expect(response.status).toBe(200);
  expect(response.body).toMatchObject({
    id: 'control-001',
    name: 'Independent read control',
  });
  expect(response.evidence.redacted).toBe(true);
});
