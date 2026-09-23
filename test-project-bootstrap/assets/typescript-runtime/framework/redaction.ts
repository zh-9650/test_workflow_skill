const SECRET_KEYS = /authorization|cookie|token|password|secret|api[_-]?key/i;

export function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        SECRET_KEYS.test(key) ? '[REDACTED]' : redact(item),
      ]),
    );
  }
  return value;
}
