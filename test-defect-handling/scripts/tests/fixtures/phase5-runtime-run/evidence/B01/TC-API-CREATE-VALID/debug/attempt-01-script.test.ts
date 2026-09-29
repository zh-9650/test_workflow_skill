import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { saveJsonEvidence } from '../../../../../test-automation/framework/evidence.js';
import { request } from '../../../../../test-automation/framework/api-client.js';

const caseId = 'TC-API-CREATE-VALID';
const expectedId = 'A-TC-API-CREATE-VALID';
const runDirectory = resolve(process.cwd(), '../test-runs/PHASE5-RUN-002');
const evidencePath = resolve(
  runDirectory,
  'evidence/B01/TC-API-CREATE-VALID/api/create-request-response.json',
);

test(`${caseId}: create valid item`, async () => {
  const baseUrl = process.env.PHASE5_BASE_URL ?? 'http://127.0.0.1:4174';
  const response = await request({
    method: 'POST',
    url: `${baseUrl}/api/items`,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ id: 'item-phase5-b01', name: 'Phase5 Item' }),
    timeoutMs: 5_000,
  });

  await saveJsonEvidence(evidencePath, {
    run_id: 'PHASE5-RUN-002',
    batch_id: 'B01',
    case_id: caseId,
    expected_id: expectedId,
    expected: '201 response contains id=item-phase5-b01 and name=Phase5 Item',
    actual: {
      status: response.status,
      body: response.body,
    },
    result: {
      status_is_201: response.status === 201,
      body_contains_expected_identity:
        typeof response.body === 'object' && response.body !== null &&
        'id' in response.body && response.body.id === 'item-phase5-b01' &&
        'name' in response.body && response.body.name === 'Phase5 Item',
    },
    api_evidence: response.evidence,
  });

  expect(response.status).toBe(201);
  expect(response.body).toMatchObject({ id: 'item-phase5-b01', name: 'Phase5 Item' });
});
