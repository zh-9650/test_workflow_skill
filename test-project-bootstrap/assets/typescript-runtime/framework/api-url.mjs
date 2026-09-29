export function resolveApiUrl(path, apiBaseUrl) {
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || path.includes('\\')) {
    throw new Error('API request path must be an origin-relative path beginning with one slash');
  }
  let base;
  try { base = new URL(apiBaseUrl); } catch { throw new Error('API base URL must be absolute'); }
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash) {
    throw new Error('API base URL must be HTTP(S) without credentials, query, or fragment');
  }
  const target = new URL(path, base);
  if (target.origin !== base.origin) throw new Error('API request target must remain on the current Run API origin');
  return target.href;
}
