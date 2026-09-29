import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolveApiUrl } from '../../assets/typescript-runtime/framework/api-url.mjs';

test('resolves an origin-relative API path against the bound Run base URL', () => {
  assert.equal(resolveApiUrl('/api/items', 'http://127.0.0.1:44174'), 'http://127.0.0.1:44174/api/items');
});

test('rejects absolute, protocol-relative, or backslash paths that could escape the bound origin', () => {
  for (const path of ['http://127.0.0.1:4174/api/items', '//127.0.0.1:4174/api/items', '\\\\127.0.0.1\\api']) {
    assert.throws(() => resolveApiUrl(path, 'http://127.0.0.1:44174'));
  }
});

test('rejects a base URL containing credentials, query, or fragment', () => {
  for (const base of ['http://user:pass@127.0.0.1:44174', 'http://127.0.0.1:44174?x=1', 'http://127.0.0.1:44174/#x']) {
    assert.throws(() => resolveApiUrl('/api/items', base));
  }
});
