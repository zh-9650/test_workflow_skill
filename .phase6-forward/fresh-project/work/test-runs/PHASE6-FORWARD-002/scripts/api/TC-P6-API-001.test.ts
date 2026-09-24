import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { request } from '../../../../test-automation/framework/api-client.js';
import { runtimeContext } from '../../../../test-automation/framework/runtime-context.js';

describe('TC-P6-API-001 item lookup', () => {
  it('returns the exact ready item and saves redacted request/response evidence', async () => {
    const context = runtimeContext();
    if (!context.apiBaseUrl) throw new Error('TEST_API_BASE_URL is required');

    const result = await request({
      method: 'GET',
      url: new URL('/api/items/1', context.apiBaseUrl).toString(),
      timeoutMs: 5000,
    });

    expect(result.status).toBe(200);
    expect(result.body).toEqual({ id: '1', name: 'Smoke item', status: 'ready' });

    const evidenceDir = join(context.runDir, 'evidence', context.batchId, 'TC-P6-API-001');
    await mkdir(evidenceDir, { recursive: true });
    await writeFile(
      join(evidenceDir, 'request-response.json'),
      `${JSON.stringify(result.evidence, null, 2)}\n`,
      'utf8',
    );
  });
});
