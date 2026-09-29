import { redact } from './redaction.js';
import { runtimeContext } from './runtime-context.js';
import { resolveApiUrl } from './api-url.mjs';

export type ApiRequest = {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path?: string;
  url?: string;
  headers?: HeadersInit;
  body?: BodyInit;
  timeoutMs: number;
};

export type ApiResponse = {
  method: ApiRequest['method'];
  url: string;
  status: number;
  headers: Headers;
  text: string;
  body: unknown;
  durationMs: number;
  correlationId: string | null;
  evidence: {
    redacted: true;
    request: { method: string; url: string; headers: Record<string, string>; body: unknown };
    response: {
      status: number;
      body: unknown;
      durationMs: number;
      correlationId: string | null;
    };
  };
};

export async function request(input: ApiRequest): Promise<ApiResponse> {
  if (!Number.isFinite(input.timeoutMs) || input.timeoutMs <= 0) {
    throw new RangeError('timeoutMs must be an explicit positive finite number');
  }

  const targetPath = input.path ?? input.url;
  if (!targetPath) {
    throw new Error('ApiRequest requires non-empty path or url');
  }

  const requestHeaders = new Headers(input.headers);
  const context = runtimeContext();
  if (!context.apiBaseUrl) throw new Error('API RuntimeContext is missing the current Run base URL');
  const url = resolveApiUrl(targetPath, context.apiBaseUrl);
  let requestBody: unknown = input.body ?? null;
  if (typeof input.body === 'string') {
    try {
      requestBody = JSON.parse(input.body) as unknown;
    } catch {
      requestBody = input.body;
    }
  }
  const started = performance.now();
  const response = await fetch(url, {
    method: input.method,
    headers: requestHeaders,
    body: input.body,
    signal: AbortSignal.timeout(input.timeoutMs),
  });
  const text = await response.text();
  let body: unknown = text;
  try {
    body = JSON.parse(text) as unknown;
  } catch {
    // Keep non-JSON responses as text for both assertions and evidence.
  }
  const durationMs = Math.round(performance.now() - started);
  const correlationId = response.headers.get('x-request-id') ??
    response.headers.get('x-correlation-id');
  const evidence = redact({
    redacted: true,
    request: {
      method: input.method,
      url,
      headers: Object.fromEntries(requestHeaders.entries()),
      body: requestBody,
    },
    response: { status: response.status, body, durationMs, correlationId },
  }) as ApiResponse['evidence'];
  return {
    method: input.method,
    url,
    status: response.status,
    headers: response.headers,
    text,
    body,
    durationMs,
    correlationId,
    evidence,
  };
}
