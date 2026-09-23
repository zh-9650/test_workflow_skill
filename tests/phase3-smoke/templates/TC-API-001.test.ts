import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { request } from '../../../../../../work/test-automation/framework/api-client.js';
import { saveJsonEvidence } from '../../../../../../work/test-automation/framework/evidence.js';
import { runtimeContext } from '../../../../../../work/test-automation/framework/runtime-context.js';

test('TC-API-001 reads a resource through Node native fetch', async () => {
  const context = runtimeContext();
  if (!context.apiBaseUrl) throw new Error('TEST_API_BASE_URL is required');
  const url = new URL('/api/items/1', context.apiBaseUrl).toString();
  const response = await request({
    method: 'GET',
    url,
    headers: { authorization: 'Bearer smoke-secret' },
  });
  expect(response.status).toBe(200);
  expect(JSON.parse(response.text)).toEqual({ id: '1', name: 'Smoke item', status: 'ready' });

  const evidenceDir = resolve(context.runDir, 'evidence');
  await mkdir(evidenceDir, { recursive: true });
  await saveJsonEvidence(resolve(evidenceDir, 'TC-API-001-request-response.json'), {
    request: { method: 'GET', url, authorization: 'Bearer smoke-secret' },
    response: { status: response.status, body: JSON.parse(response.text) },
  });
});
