const SENSITIVE_TOKENS = new Set([
  'authorization', 'auth', 'credential', 'credentials', 'cookie', 'token',
  'password', 'secret', 'apikey', 'session', 'email', 'phone', 'mobile',
  'telephone', 'national', 'idcard', 'passport', 'ssn', 'creditcard',
  'cardnumber', 'bankaccount', 'accountnumber',
]);

const SAFE_STATUS_VALUES = new Set([
  'active', 'absent', 'closed', 'expired', 'failed', 'invalid', 'none', 'open',
  'present', 'sent', 'success', 'unset', 'valid', 'verified',
]);
const SAFE_TYPE_VALUES = new Set([
  'access', 'basic', 'bearer', 'business', 'digest', 'home', 'oauth', 'other',
  'personal', 'refresh', 'work',
]);
const INLINE_SENSITIVE_VALUES = [
  /\bBearer\s+[A-Za-z0-9._~+/=-]{8,}/gi,
  /\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,
  /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
  /(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)/g,
];

function normalizedTokens(key: string): string[] {
  return key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase().match(/[a-z0-9]+/g) ?? [];
}

function isSensitiveField(key: string, value: unknown): boolean {
  const tokens = normalizedTokens(key);
  const tokenSet = new Set(tokens);
  const joined = `_${tokens.join('_')}_`;
  const sensitive = tokens.some((token) => SENSITIVE_TOKENS.has(token)) ||
    ['api_key', 'access_key', 'private_key', 'secret_key', 'credit_card',
      'card_number', 'bank_account', 'account_number', 'national_id', 'id_card']
      .some((field) => joined.includes(`_${field}_`));
  if (!sensitive) return false;
  if (value == null || value === '') return false;
  const metadata = ['status', 'verified', 'valid', 'enabled', 'configured', 'count', 'length', 'type']
    .some((token) => tokenSet.has(token));
  if (!metadata) return true;
  if (typeof value === 'boolean') return false;
  if ((tokenSet.has('count') || tokenSet.has('length')) &&
      typeof value === 'number' && Number.isInteger(value) && value >= 0) return false;
  if (typeof value === 'string' && tokenSet.has('status') && SAFE_STATUS_VALUES.has(value.toLowerCase())) return false;
  if (typeof value === 'string' && tokenSet.has('type') && SAFE_TYPE_VALUES.has(value.toLowerCase())) return false;
  return true;
}

function redactString(value: string): string {
  const pemSafe = value.replace(
    /-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----[\s\S]*?(?:-----END \1-----|$)/g,
    '[REDACTED]',
  );
  const assignmentsSafe = pemSafe.replace(
    /(^|[?&;\s])([^=&#;\s]+)=([^&#;\s]*)/g,
    (match, prefix: string, key: string, secret: string) =>
      isSensitiveField(key, secret) ? `${prefix}${key}=[REDACTED]` : match,
  );
  return INLINE_SENSITIVE_VALUES.reduce(
    (result, pattern) => result.replace(pattern, '[REDACTED]'),
    assignmentsSafe,
  );
}

export function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        isSensitiveField(key, item) ? '[REDACTED]' : redact(item),
      ]),
    );
  }
  if (typeof value === 'string') return redactString(value);
  return value;
}
