export type ApiRequest = {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  url: string;
  headers?: HeadersInit;
  body?: BodyInit;
  timeoutMs?: number;
};

export type ApiResponse = {
  status: number;
  headers: Headers;
  text: string;
  durationMs: number;
};

export async function request(input: ApiRequest): Promise<ApiResponse> {
  const started = performance.now();
  const response = await fetch(input.url, {
    method: input.method,
    headers: input.headers,
    body: input.body,
    signal: AbortSignal.timeout(input.timeoutMs ?? 30_000),
  });
  return {
    status: response.status,
    headers: response.headers,
    text: await response.text(),
    durationMs: Math.round(performance.now() - started),
  };
}
