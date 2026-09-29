/**
 * TypeSafe Jev Runtime Adapter
 *
 * Provides bounded, audited invocations for:
 * 1. UI candidate resolution from real-page visible candidates
 * 2. API bounded semantic evaluation on redacted response excerpts
 *
 * Invariants:
 * - Uses Node native fetch
 * - Bounded input sizes and strictly parsed output schema
 * - Fixed provider and model; NO fallback to Laya or other providers
 * - Strict budget tracking; aborts immediately when cost cap is reached
 * - Credentials are never logged or stored in output artifacts
 */

import { createHash } from 'node:crypto';

export type JevConfig = {
  endpoint: string;
  apiKey: string;
  model: string;
  budgetCapUsd?: number;
  timeoutMs: number;
};

export type JevUiCandidate = {
  id: string;
  tag: string;
  role?: string;
  text?: string;
  ariaLabel?: string;
  visible: boolean;
  enabled: boolean;
};

export type JevUiRequest = {
  kind: 'ui_candidate_selection';
  stepDescription: string;
  candidates: JevUiCandidate[];
  contextSummary?: string;
};

export type JevUiResponse = {
  selectedId: string;
  confidence: number;
  rationale: string;
  usage: { promptTokens: number; completionTokens: number; estimatedCostUsd: number };
  requestSha256: string;
  responseSha256: string;
  model: string;
  durationMs: number;
};

export type JevApiSemanticRequest = {
  kind: 'api_semantic_judgment';
  evaluationGoal: string;
  responseExcerpt: string;
  options: string[]; // e.g. ["supported", "contradicted", "insufficient_evidence"]
};

export type JevApiSemanticResponse = {
  selectedOption: string;
  confidence: number;
  rationale: string;
  usage: { promptTokens: number; completionTokens: number; estimatedCostUsd: number };
  requestSha256: string;
  responseSha256: string;
  model: string;
  durationMs: number;
};

export type JevErrorType =
  | 'timeout'
  | 'auth_failed'
  | 'rate_limited'
  | 'insufficient_balance'
  | 'budget_exceeded'
  | 'schema_mismatch'
  | 'candidate_not_found'
  | 'invalid_candidate'
  | 'provider_error';

export class JevAdapterError extends Error {
  readonly type: JevErrorType;
  constructor(type: JevErrorType, message: string) {
    super(`[JevAdapter:${type}] ${message}`);
    this.type = type;
    this.name = 'JevAdapterError';
  }
}

let cumulativeCostUsd = 0;

export function getCumulativeCost(): number {
  return cumulativeCostUsd;
}

export function resetCumulativeCost(): void {
  cumulativeCostUsd = 0;
}

function sha256(data: string): string {
  return createHash('sha256').update(data, 'utf-8').digest('hex');
}

/**
 * Select a UI candidate ID from a bounded set of real-page candidates.
 */
export async function selectUiCandidate(
  req: JevUiRequest,
  config: JevConfig
): Promise<JevUiResponse> {
  if (!req.candidates || req.candidates.length === 0) {
    throw new JevAdapterError('schema_mismatch', 'candidates list must not be empty');
  }
  const validIds = new Set(req.candidates.map((c) => c.id));
  if (validIds.size !== req.candidates.length) {
    throw new JevAdapterError('schema_mismatch', 'candidate IDs must be unique');
  }

  for (const c of req.candidates) {
    if (!c.visible || !c.enabled) {
      throw new JevAdapterError('invalid_candidate', `Candidate "${c.id}" must be visible and enabled before Jev invocation`);
    }
  }

  if (config.budgetCapUsd !== undefined && config.budgetCapUsd !== null) {
    if (cumulativeCostUsd >= config.budgetCapUsd) {
      throw new JevAdapterError('budget_exceeded', `Jev cumulative cost $${cumulativeCostUsd.toFixed(4)} reached budget cap $${config.budgetCapUsd.toFixed(4)}`);
    }
  }

  const payload = {
    model: config.model,
    state: {
      step: req.stepDescription,
      context: req.contextSummary ?? '',
      candidates: req.candidates.map((c) => ({
        id: c.id,
        tag: c.tag,
        role: c.role ?? '',
        name: (c.text ?? c.ariaLabel ?? '').slice(0, 100),
        visible: c.visible,
        enabled: c.enabled,
      })),
    },
    questions: {
      select_candidate: {
        type: 'choice',
        instructions: `Choose exactly one supplied candidate ID that best matches: "${req.stepDescription}". Do not invent selectors or actions.`,
        criteria: Object.fromEntries(
          req.candidates.map((c) => [
            c.id,
            `Candidate ${c.id}: ${c.text || c.ariaLabel || c.role || c.tag}`,
          ])
        ),
      },
    },
  };

  const payloadStr = JSON.stringify(payload);
  const reqHash = sha256(payloadStr);

  const start = performance.now();
  let resText: string;
  try {
    const res = await fetch(config.endpoint, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${config.apiKey}`,
        'x-jev-task': 'ui_candidate_selection',
      },
      body: payloadStr,
      signal: AbortSignal.timeout(config.timeoutMs),
    });

    if (res.status === 401 || res.status === 403) {
      throw new JevAdapterError('auth_failed', `Authentication failed with status ${res.status}`);
    }
    if (res.status === 402) {
      throw new JevAdapterError('insufficient_balance', 'Jev API insufficient balance / payment required');
    }
    if (res.status === 429) {
      throw new JevAdapterError('rate_limited', 'Jev API rate limit exceeded');
    }
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      if (/balance|quota|insufficient|arrears|欠费/i.test(errText)) {
        throw new JevAdapterError('insufficient_balance', `Jev API insufficient balance: ${errText}`);
      }
      throw new JevAdapterError('provider_error', `Jev API error status ${res.status}: ${errText}`);
    }

    const MAX_RESPONSE_BYTES = 1024 * 1024;
    const contentLength = Number(res.headers.get('content-length') || 0);
    if (contentLength > MAX_RESPONSE_BYTES) {
      throw new JevAdapterError('provider_error', `Jev response size ${contentLength} exceeds limit of ${MAX_RESPONSE_BYTES} bytes`);
    }
    resText = await res.text();
    if (resText.length > MAX_RESPONSE_BYTES) {
      throw new JevAdapterError('provider_error', `Jev response length ${resText.length} exceeds limit of ${MAX_RESPONSE_BYTES} characters`);
    }
  } catch (err: unknown) {
    if (err instanceof JevAdapterError) throw err;
    if ((err as Error)?.name === 'TimeoutError' || (err as Error)?.name === 'AbortError') {
      throw new JevAdapterError('timeout', `Jev request timed out after ${config.timeoutMs}ms`);
    }
    throw new JevAdapterError('provider_error', `Network error: ${(err as Error)?.message}`);
  }

  const durationMs = Math.round(performance.now() - start);
  const resHash = sha256(resText);

  let parsed: any;
  try {
    parsed = JSON.parse(resText);
  } catch {
    throw new JevAdapterError('schema_mismatch', 'Jev response is not valid JSON');
  }

  const ans = parsed.answers?.select_candidate;
  const selectedId = ans ? ans.choice : (parsed.selected_id ?? parsed.selectedId);
  const confidence = Number(ans ? (ans.confidence ?? 1.0) : (parsed.confidence ?? 0));
  const rationale = String(ans ? JSON.stringify(ans.probabilities ?? {}) : (parsed.rationale ?? ''));

  if (typeof selectedId !== 'string' || !selectedId) {
    throw new JevAdapterError('schema_mismatch', 'selected_id is missing or invalid');
  }
  if (!validIds.has(selectedId)) {
    throw new JevAdapterError(
      'candidate_not_found',
      `Jev selected ID "${selectedId}" which was not in the provided candidates`
    );
  }
  if (typeof confidence !== 'number' || !Number.isFinite(confidence) || confidence < 0.0 || confidence > 1.0) {
    throw new JevAdapterError('schema_mismatch', `Jev response confidence must be a finite number between 0.0 and 1.0, got ${confidence}`);
  }

  const estCost = Number(parsed.estimated_cost_usd ?? 0.001);
  cumulativeCostUsd += estCost;

  return {
    selectedId,
    confidence,
    rationale,
    usage: {
      promptTokens: Number(parsed.usage?.input_tokens ?? parsed.usage?.prompt_tokens ?? 0),
      completionTokens: Number(parsed.usage?.output_tokens ?? parsed.usage?.completion_tokens ?? 0),
      estimatedCostUsd: estCost,
    },
    requestSha256: reqHash,
    responseSha256: resHash,
    model: config.model,
    durationMs,
  };
}

/**
 * Perform a bounded semantic evaluation on an API response excerpt.
 */
export async function evaluateApiSemantics(
  req: JevApiSemanticRequest,
  config: JevConfig
): Promise<JevApiSemanticResponse> {
  if (!req.options || req.options.length < 2) {
    throw new JevAdapterError('schema_mismatch', 'At least two options are required');
  }
  const validOptions = new Set(req.options);

  if (config.budgetCapUsd !== undefined && config.budgetCapUsd !== null) {
    if (cumulativeCostUsd >= config.budgetCapUsd) {
      throw new JevAdapterError('budget_exceeded', `Jev cumulative cost $${cumulativeCostUsd.toFixed(4)} reached budget cap $${config.budgetCapUsd.toFixed(4)}`);
    }
  }

  const payload = {
    model: config.model,
    state: {
      evaluation_goal: req.evaluationGoal,
      response_excerpt: req.responseExcerpt.slice(0, 4096),
    },
    questions: {
      evaluate_semantics: {
        type: 'choice',
        instructions: `Evaluate the response excerpt against the goal: "${req.evaluationGoal}". Choose one declared option.`,
        criteria: Object.fromEntries(
          req.options.map((opt) => [opt, `Outcome option: ${opt}`])
        ),
      },
    },
  };

  const payloadStr = JSON.stringify(payload);
  const reqHash = sha256(payloadStr);

  const start = performance.now();
  let resText: string;
  try {
    const res = await fetch(config.endpoint, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${config.apiKey}`,
        'x-jev-task': 'api_semantic_judgment',
      },
      body: payloadStr,
      signal: AbortSignal.timeout(config.timeoutMs),
    });

    if (res.status === 401 || res.status === 403) {
      throw new JevAdapterError('auth_failed', `Authentication failed with status ${res.status}`);
    }
    if (res.status === 402) {
      throw new JevAdapterError('insufficient_balance', 'Jev API insufficient balance / payment required');
    }
    if (res.status === 429) {
      throw new JevAdapterError('rate_limited', 'Jev API rate limit exceeded');
    }
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      if (/balance|quota|insufficient|arrears|欠费/i.test(errText)) {
        throw new JevAdapterError('insufficient_balance', `Jev API insufficient balance: ${errText}`);
      }
      throw new JevAdapterError('provider_error', `Jev API error status ${res.status}: ${errText}`);
    }

    const MAX_RESPONSE_BYTES = 1024 * 1024;
    const contentLength = Number(res.headers.get('content-length') || 0);
    if (contentLength > MAX_RESPONSE_BYTES) {
      throw new JevAdapterError('provider_error', `Jev response size ${contentLength} exceeds limit of ${MAX_RESPONSE_BYTES} bytes`);
    }
    resText = await res.text();
    if (resText.length > MAX_RESPONSE_BYTES) {
      throw new JevAdapterError('provider_error', `Jev response length ${resText.length} exceeds limit of ${MAX_RESPONSE_BYTES} characters`);
    }
  } catch (err: unknown) {
    if (err instanceof JevAdapterError) throw err;
    if ((err as Error)?.name === 'TimeoutError' || (err as Error)?.name === 'AbortError') {
      throw new JevAdapterError('timeout', `Jev request timed out after ${config.timeoutMs}ms`);
    }
    throw new JevAdapterError('provider_error', `Network error: ${(err as Error)?.message}`);
  }

  const durationMs = Math.round(performance.now() - start);
  const resHash = sha256(resText);

  let parsed: any;
  try {
    parsed = JSON.parse(resText);
  } catch {
    throw new JevAdapterError('schema_mismatch', 'Jev response is not valid JSON');
  }

  const ans = parsed.answers?.evaluate_semantics;
  const selectedOption = ans ? ans.choice : (parsed.selected_option ?? parsed.selectedOption);
  const confidence = Number(ans ? (ans.confidence ?? 1.0) : (parsed.confidence ?? 0));
  const rationale = String(ans ? JSON.stringify(ans.probabilities ?? {}) : (parsed.rationale ?? ''));

  if (!validOptions.has(selectedOption)) {
    throw new JevAdapterError(
      'schema_mismatch',
      `Selected option "${selectedOption}" is not in declared options [${req.options.join(', ')}]`
    );
  }
  if (typeof confidence !== 'number' || !Number.isFinite(confidence) || confidence < 0.0 || confidence > 1.0) {
    throw new JevAdapterError('schema_mismatch', `Jev response confidence must be a finite number between 0.0 and 1.0, got ${confidence}`);
  }

  const estCost = Number(parsed.estimated_cost_usd ?? 0.001);
  cumulativeCostUsd += estCost;

  return {
    selectedOption,
    confidence,
    rationale,
    usage: {
      promptTokens: Number(parsed.usage?.input_tokens ?? parsed.usage?.prompt_tokens ?? 0),
      completionTokens: Number(parsed.usage?.output_tokens ?? parsed.usage?.completion_tokens ?? 0),
      estimatedCostUsd: estCost,
    },
    requestSha256: reqHash,
    responseSha256: resHash,
    model: config.model,
    durationMs,
  };
}
