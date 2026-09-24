import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { request } from '../../../../test-automation/framework/api-client.js';
import { saveJsonEvidence } from '../../../../test-automation/framework/evidence.js';
import { runtimeContext } from '../../../../test-automation/framework/runtime-context.js';

const FIXTURE_BASE_URL = 'http://127.0.0.1:41739';

describe('TC-P6-API-001 GET /api/items/1 returns the exact ready smoke item', () => {
  it('returns HTTP 200 with exact JSON and a string id', async () => {
    const context = runtimeContext();

    const response = await request({
      method: 'GET',
      url: `${FIXTURE_BASE_URL}/api/items/1`,
      timeoutMs: 5000,
    });

    // Persist redacted request/response evidence before assertions so failures
    // still leave an artifact for diagnosis.
    await saveJsonEvidence(
      join(context.runDir, 'evidence', context.batchId, 'TC-P6-API-001', 'request-response.json'),
      response.evidence,
    );

    expect(response.status).toBe(200);

    const body = response.body as { id?: unknown; name?: unknown; status?: unknown };
    expect(body).toEqual({ id: '1', name: 'Smoke item', status: 'ready' });
    expect(typeof body.id).toBe('string');
  });
});
