import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from 'vitest';
import { request } from '../../../../../../work/test-automation/framework/api-client.js';
import { saveJsonEvidence } from '../../../../../../work/test-automation/framework/evidence.js';
import { redact } from '../../../../../../work/test-automation/framework/redaction.js';
import { runtimeContext } from '../../../../../../work/test-automation/framework/runtime-context.js';

test('TC-API-001 reads a resource through Node native fetch', async () => {
  const context = runtimeContext();
  if (!context.apiBaseUrl) throw new Error('TEST_API_BASE_URL is required');
  const url = new URL('/api/items/1', context.apiBaseUrl).toString();
  const response = await request({
    method: 'GET',
    url,
    headers: { authorization: 'Bearer smoke-secret' },
    timeoutMs: 5_000,
  });
  expect(response.status).toBe(200);
  expect(response.body).toEqual({ id: '1', name: 'Smoke item', status: 'ready' });
  expect(response.method).toBe('GET');
  expect(response.url).toBe(url);
  expect(
    response.correlationId === null || response.correlationId.length > 0,
  ).toBe(true);

  const pem = '-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\\n-----END PRIVATE KEY-----';
  const redactedProbe = redact({
    url: 'https://example.test/?access_token=smoke-secret-value',
    api_key: 'smoke-secret-value',
    pem,
  }) as { url: string; api_key: string; pem: string };
  expect(redactedProbe.url).toContain('access_token=[REDACTED]');
  expect(redactedProbe.api_key).toBe('[REDACTED]');
  expect(redactedProbe.pem).toBe('[REDACTED]');

  const evidenceDir = resolve(context.runDir, 'evidence');
  await mkdir(evidenceDir, { recursive: true });
  await saveJsonEvidence(resolve(evidenceDir, 'TC-API-001-request-response.json'), {
    ...response.evidence,
    case_id: 'TC-API-001',
    expected_id: 'E1',
  });
});
