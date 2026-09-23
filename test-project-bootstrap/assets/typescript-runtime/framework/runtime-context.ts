import { resolve } from 'node:path';

export type RuntimeContext = {
  runDir: string;
  batchId: string;
  apiBaseUrl?: string;
  webBaseUrl?: string;
};

export function runtimeContext(env: NodeJS.ProcessEnv = process.env): RuntimeContext {
  if (!env.TEST_RUN_DIR || !env.TEST_BATCH_ID) {
    throw new Error('TEST_RUN_DIR and TEST_BATCH_ID are required');
  }
  return {
    runDir: resolve(env.TEST_RUN_DIR),
    batchId: env.TEST_BATCH_ID,
    apiBaseUrl: env.TEST_API_BASE_URL,
    webBaseUrl: env.TEST_WEB_BASE_URL,
  };
}
