import { mkdir, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { redact } from './redaction.js';

export async function saveJsonEvidence(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(redact(value), null, 2)}\n`, 'utf8');
}
