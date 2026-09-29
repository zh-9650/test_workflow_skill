import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { saveJsonEvidence } from '../../../../../test-automation/framework/evidence.js';
import { request } from '../../../../../test-automation/framework/api-client.js';

const caseId = 'TC-API-CREATE-VALID';
const expectedId = 'A-TC-API-CREATE-VALID';
const runDirectory = resolve(
  process.env.TEST_RUN_DIR ?? resolve(process.cwd(), '../test-runs/PHASE5-RUN-002'),
);
const evidencePath = resolve(
  runDirectory,
  'evidence/B01/TC-API-CREATE-VALID/api/create-request-response.json',
);

test(`${caseId}: create valid item`, async () => {
  const baseUrl = process.env.PHASE5_API_BASE_URL ?? 'http://127.0.0.1:4174';
  const response = await request({
    method: 'POST',
    url: `${baseUrl}/api/items`,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ id: 'item-phase5-b01', name: 'Phase5 Item' }),
    timeoutMs: 5_000,
  });

  await saveJsonEvidence(evidencePath, response.evidence);

  expect(response.status).toBe(201);
  expect(response.body).toMatchObject({ id: 'item-phase5-b01', name: 'Phase5 Item' });
});
