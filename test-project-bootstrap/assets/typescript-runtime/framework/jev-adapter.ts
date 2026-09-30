/** Bounded official TypeSafe Choice transport. Callers retain judgment and action ownership. */
import { createHash } from 'node:crypto';

export type JevConfig = {
  endpoint: string; apiKey: string; model: string; modelVersion: string;
  budgetCapUsd: number; maxCostPerCallUsd: number; maxCalls: number;
  maxInputChars: number; timeoutMs: number;
};
export type JevUiCandidate = { id: string; tag: string; role?: string; text?: string; ariaLabel?: string; visible: boolean; enabled: boolean };
export type JevUiSnapshot = { snapshotId: string; pageUrl: string; capturedAt: string; candidates: JevUiCandidate[] };
export type JevUiRequest = { kind: 'ui_candidate_selection'; stepDescription: string; snapshot: JevUiSnapshot; contextSummary?: string };
export type JevApiSemanticRequest = { kind: 'api_semantic_judgment'; evaluationGoal: string; responseExcerpt: string; options: string[] };
export type JevResponse = {
  selectedOption: string; confidence: number; probabilities: Record<string, number>;
  usage: { promptTokens: number; completionTokens: number; costUsd: number | null; reservedCostUsd: number };
  request: unknown; response: unknown; requestSha256: string; responseSha256: string; model: string; durationMs: number;
};
export type JevApiSemanticResponse = JevResponse;
export type JevUiResponse = JevResponse & { selectedId: string; postSelectionSnapshot: JevUiSnapshot };
export class JevAdapterError extends Error {
  readonly type: string;
  constructor(type: string, message: string) { super(`[JevAdapter:${type}] ${message}`); this.type=type; }
}
export class JevBudget {
  private reserved = 0;
  private calls = 0;
  reserve(config: JevConfig): void {
    if (this.calls >= config.maxCalls || this.reserved + config.maxCostPerCallUsd > config.budgetCapUsd + 1e-12) {
      throw new JevAdapterError('budget_exceeded', 'Planned calls or worst-case budget exhausted');
    }
    this.calls += 1; this.reserved += config.maxCostPerCallUsd;
  }
  get reservedCostUsd(): number { return this.reserved; }
}
const digest = (text: string): string => createHash('sha256').update(text).digest('hex');
function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new JevAdapterError('schema_mismatch', 'Object required');
  return value as Record<string, unknown>;
}
function number(value: unknown, integer = false): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || (integer && !Number.isInteger(value))) throw new JevAdapterError('schema_mismatch', 'Finite non-negative number required');
  return value;
}
function validateConfig(config: JevConfig): void {
  if (config.endpoint !== 'https://api.typesafe.ai/v1/systemone') throw new JevAdapterError('provider_error', 'Only the official pinned endpoint is allowed');
  if (!config.apiKey || !/^jev-\d+\.\d+\.\d+$/.test(config.model) || config.model !== `jev-${config.modelVersion}`) throw new JevAdapterError('schema_mismatch', 'Credential and pinned model/version required');
  for (const value of [config.budgetCapUsd, config.maxCostPerCallUsd, config.maxCalls, config.maxInputChars, config.timeoutMs]) {
    if (number(value) === 0) throw new JevAdapterError('schema_mismatch', 'Positive limits required');
  }
  if (!Number.isInteger(config.maxCalls) || !Number.isInteger(config.maxInputChars) || config.maxCostPerCallUsd > config.budgetCapUsd) throw new JevAdapterError('schema_mismatch', 'Invalid planned limits');
}
async function decide(state: unknown, goal: string, options: string[], config: JevConfig, budget: JevBudget): Promise<JevResponse> {
  validateConfig(config);
  if (!goal || options.length < 2 || options.length > 255 || new Set(options).size !== options.length || options.some(x => !x)) throw new JevAdapterError('schema_mismatch', 'Bounded unique Choice options and goal required');
  const request = { model: config.model, state, questions: { judgment: { type: 'choice', instructions: goal, criteria: Object.fromEntries(options.map(x => [x, x])) } } };
  const body = JSON.stringify(request);
  if (body.length > config.maxInputChars) throw new JevAdapterError('input_exceeded', 'Request exceeds confirmed input limit');
  budget.reserve(config); // Retain worst-case reservation even on timeout or malformed response.
  const started = performance.now(); let response: Response;
  try {
    response = await fetch(config.endpoint, { method: 'POST', redirect: 'error',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${config.apiKey}` },
      body, signal: AbortSignal.timeout(config.timeoutMs) });
  } catch { throw new JevAdapterError('provider_error', 'Request failed; reservation retained, no automatic retry'); }
  if (!response.ok) throw new JevAdapterError('provider_error', `HTTP ${response.status}; reservation retained`);
  const reader = response.body?.getReader();
  if (!reader) throw new JevAdapterError('schema_mismatch', 'Missing response body');
  const chunks: Uint8Array[] = []; let size = 0;
  while (true) {
    const part = await reader.read(); if (part.done) break;
    size += part.value.byteLength;
    if (size > 1024 * 1024) { await reader.cancel(); throw new JevAdapterError('schema_mismatch', 'Response exceeds 1 MiB'); }
    chunks.push(part.value);
  }
  const raw = Buffer.concat(chunks).toString('utf8'); let parsed: Record<string, unknown>;
  try { parsed = object(JSON.parse(raw)); } catch { throw new JevAdapterError('schema_mismatch', 'Invalid JSON envelope'); }
  if (parsed.model !== config.model) throw new JevAdapterError('schema_mismatch', 'Resolved model differs from pinned model');
  const answer = object(object(parsed.answers).judgment);
  if (answer.type !== 'choice' || typeof answer.choice !== 'string' || !options.includes(answer.choice)) throw new JevAdapterError('schema_mismatch', 'Unknown Choice answer');
  const confidence = number(answer.confidence);
  if (confidence > 1) throw new JevAdapterError('schema_mismatch', 'Confidence outside [0,1]');
  const distribution = object(answer.probabilities); const probabilities: Record<string, number> = {};
  if (Object.keys(distribution).sort().join('\0') !== [...options].sort().join('\0')) throw new JevAdapterError('schema_mismatch', 'Probability options differ');
  let sum = 0;
  for (const option of options) { const p = number(distribution[option]); if (p > 1) throw new JevAdapterError('schema_mismatch', 'Probability outside [0,1]'); probabilities[option] = p; sum += p; }
  if (Math.abs(sum - 1) > 0.05 || probabilities[answer.choice] < Math.max(...Object.values(probabilities))) throw new JevAdapterError('schema_mismatch', 'Invalid distribution or selected option');
  const usage = object(parsed.usage); const costUsd = usage.cost === undefined ? null : number(usage.cost);
  if (costUsd !== null && costUsd > config.maxCostPerCallUsd) throw new JevAdapterError('budget_exceeded', 'Reported charge exceeds per-call reservation');
  return { selectedOption: answer.choice, confidence, probabilities,
    usage: { promptTokens: number(usage.input_tokens, true), completionTokens: number(usage.output_tokens, true), costUsd, reservedCostUsd: config.maxCostPerCallUsd },
    request, response: parsed, requestSha256: digest(body), responseSha256: digest(raw), model: config.model, durationMs: Math.round(performance.now() - started) };
}
export async function evaluateApiSemantics(req: JevApiSemanticRequest, config: JevConfig, budget: JevBudget): Promise<JevApiSemanticResponse> {
  if (req.kind !== 'api_semantic_judgment' || !req.responseExcerpt) throw new JevAdapterError('schema_mismatch', 'API source response required');
  return decide({ response_excerpt: req.responseExcerpt }, req.evaluationGoal, req.options, config, budget);
}
export async function selectUiCandidate(req: JevUiRequest, config: JevConfig, budget: JevBudget, freshSnapshot: () => Promise<JevUiSnapshot>): Promise<JevUiResponse> {
  const snapshot = req.snapshot;
  const recent=(timestamp: string, now=Date.now())=>Number.isFinite(Date.parse(timestamp)) && Date.parse(timestamp)<=now && now-Date.parse(timestamp)<=30000;
  if (req.kind !== 'ui_candidate_selection' || !snapshot.snapshotId || !snapshot.pageUrl || !Number.isFinite(Date.parse(snapshot.capturedAt))) throw new JevAdapterError('invalid_candidate', 'Real page snapshot identity, URL and timestamp required');
  if (snapshot.candidates.some(c => !c.visible || !c.enabled)) throw new JevAdapterError('invalid_candidate', 'Candidates must be visible and enabled');
  if (!recent(snapshot.capturedAt)) throw new JevAdapterError('invalid_candidate', 'Candidate snapshot is expired or from the future');
  const result = await decide({ snapshot, context: req.contextSummary ?? '' }, req.stepDescription, snapshot.candidates.map(c => c.id), config, budget);
  const revalidationStarted=Date.now();
  const fresh = await freshSnapshot(); const original = snapshot.candidates.find(c => c.id === result.selectedOption);
  const selected = fresh.candidates.filter(c => c.id === result.selectedOption);
  if (fresh.pageUrl !== snapshot.pageUrl || fresh.snapshotId === snapshot.snapshotId || !recent(fresh.capturedAt) || Date.parse(fresh.capturedAt)<revalidationStarted || Date.parse(fresh.capturedAt) <= Date.parse(snapshot.capturedAt)
    || selected.length !== 1 || JSON.stringify(selected[0]) !== JSON.stringify(original)) throw new JevAdapterError('invalid_candidate', 'Selected candidate changed or lacks fresh revalidation');
  return { ...result, selectedId: result.selectedOption, postSelectionSnapshot: fresh };
}
