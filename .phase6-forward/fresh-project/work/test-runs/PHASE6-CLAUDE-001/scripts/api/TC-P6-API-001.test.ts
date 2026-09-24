import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { request } from '../../../../test-automation/framework/api-client.js';
import { saveJsonEvidence } from '../../../../test-automation/framework/evidence.js';
import { runtimeContext } from '../../../../test-automation/framework/runtime-context.js';

describe('TC-P6-API-001 item lookup', () => {
  it('GET /api/items/1 returns HTTP 200 and the exact ready item', async () => {
    const context = runtimeContext();
    if (!context.apiBaseUrl) throw new Error('TEST_API_BASE_URL is required');

    const result = await request({
      method: 'GET',
      url: new URL('/api/items/1', context.apiBaseUrl).toString(),
      timeoutMs: 5000,
    });

    expect(result.status).toBe(200);
    expect(result.body).toEqual({ id: '1', name: 'Smoke item', status: 'ready' });
    expect(typeof (result.body as { id: unknown }).id).toBe('string');

    const evidencePath = join(
      context.runDir,
      'evidence',
      context.batchId,
      'TC-P6-API-001',
      'request-response.json',
    );
    await saveJsonEvidence(evidencePath, result.evidence);
  });
});
