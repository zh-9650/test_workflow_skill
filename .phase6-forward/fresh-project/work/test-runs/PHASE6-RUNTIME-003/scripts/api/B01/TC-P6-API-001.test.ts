import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { expect, test } from 'vitest';
import { request } from '../../../../../test-automation/framework/api-client.js';
import { runtimeContext } from '../../../../../test-automation/framework/runtime-context.js';
import { saveJsonEvidence } from '../../../../../test-automation/framework/evidence.js';

const context = runtimeContext();
const caseDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-API-001');

test('TC-P6-API-001 exact frozen item response', async () => {
  if (!context.apiBaseUrl) throw new Error('TEST_API_BASE_URL is required');

  const response = await request({
    method: 'GET',
    url: new URL('/api/items/1', context.apiBaseUrl).toString(),
    timeoutMs: 10_000,
  });

  await expect(response.status).toBe(200);
  expect(response.body).toEqual({ id: '1', name: 'Smoke item', status: 'ready' });
  expect(typeof (response.body as { id?: unknown }).id).toBe('string');

  const apiDir = join(caseDir, 'api');
  await mkdir(apiDir, { recursive: true });
  await saveJsonEvidence(join(apiDir, 'request-response.json'), response.evidence);
});
