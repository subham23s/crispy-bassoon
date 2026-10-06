import test from 'node:test';
import assert from 'node:assert/strict';
import { createApiClient, ApiError } from '../api-client.mjs';
import { createStaticServer } from '../server.mjs';

function mockResponse(status, body = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    async json() {
      return body;
    },
  };
}

function headerValue(options, name) {
  return options.headers?.get?.(name) || options.headers?.[name] || options.headers?.[name.toLowerCase()];
}

function listen(server) {
  return new Promise((resolve) => server.listen(0, () => resolve(server.address().port)));
}

function close(server) {
  return new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}

test('auth stores tokens in memory, sends Bearer, refreshes once, and logs out authenticated', async () => {
  const calls = [];
  const fetchMock = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith('/auth/login')) return mockResponse(200, { user: { email: 'analyst@example.test' }, access_token: 'access-1', refresh_token: 'refresh-1' });
    if (url.endsWith('/chat/query') && calls.filter((call) => call.url.endsWith('/chat/query')).length === 1) return mockResponse(401, { detail: 'expired' });
    if (url.endsWith('/auth/refresh')) return mockResponse(200, { access_token: 'access-2', refresh_token: 'refresh-2' });
    if (url.endsWith('/chat/query')) return mockResponse(200, { answer: 'retrieved result' });
    if (url.endsWith('/auth/logout')) return mockResponse(204);
    throw new Error(`unexpected request ${url}`);
  };
  const client = createApiClient({ baseUrl: 'https://api.test', fetchImpl: fetchMock });

  const login = await client.login('analyst@example.test', 'correct horse battery staple');
  assert.equal(login.user.email, 'analyst@example.test');
  assert.equal(headerValue(calls[0].options, 'authorization'), undefined, 'login must not require an existing token');

  const query = await client.request('/chat/query', { method: 'POST', body: JSON.stringify({ query: 'test' }) });
  assert.equal(query.answer, 'retrieved result');
  const queryCalls = calls.filter((call) => call.url.endsWith('/chat/query'));
  assert.equal(queryCalls.length, 2, 'the original request should be retried once after refresh');
  assert.equal(headerValue(queryCalls[0].options, 'authorization'), 'Bearer access-1');
  assert.equal(headerValue(queryCalls[1].options, 'authorization'), 'Bearer access-2');
  assert.equal(calls.filter((call) => call.url.endsWith('/auth/refresh')).length, 1);

  await client.logout();
  const logoutCall = calls.find((call) => call.url.endsWith('/auth/logout'));
  assert.equal(headerValue(logoutCall.options, 'authorization'), 'Bearer access-2');
  assert.deepEqual(JSON.parse(logoutCall.options.body), { refresh_token: 'refresh-2' });
  assert.deepEqual(client.getSession(), { accessToken: null, refreshToken: null });
});

test('register posts only email and password and keeps returned tokens in memory', async () => {
  let call;
  const client = createApiClient({
    baseUrl: 'https://api.test',
    fetchImpl: async (url, options = {}) => {
      call = { url, options };
      return mockResponse(201, { user: { email: 'new@example.test' }, access_token: 'new-access', refresh_token: 'new-refresh' });
    },
  });

  const result = await client.register('new@example.test', 'correct horse battery staple');
  assert.equal(call.url, 'https://api.test/auth/register');
  assert.deepEqual(JSON.parse(call.options.body), {
    email: 'new@example.test',
    password: 'correct horse battery staple',
  });
  assert.equal(headerValue(call.options, 'authorization'), undefined);
  assert.deepEqual(client.getSession(), { accessToken: 'new-access', refreshToken: 'new-refresh' });
  assert.equal(result.user.email, 'new@example.test');
});

test('a second 401 clears the session and reports an API error without looping refresh', async () => {
  const calls = [];
  let expiredCount = 0;
  const fetchMock = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith('/auth/refresh')) return mockResponse(200, { access_token: 'access-2', refresh_token: 'refresh-2' });
    return mockResponse(401, { detail: 'still unauthorized' });
  };
  const client = createApiClient({
    baseUrl: 'https://api.test',
    fetchImpl: fetchMock,
    onSessionExpired: () => { expiredCount += 1; },
  });
  client.setSession({ access_token: 'access-1', refresh_token: 'refresh-1' });

  await assert.rejects(
    client.request('/documents'),
    (error) => error instanceof ApiError && error.status === 401 && error.message === 'still unauthorized',
  );
  assert.equal(calls.filter((call) => call.url.endsWith('/documents')).length, 2);
  assert.equal(calls.filter((call) => call.url.endsWith('/auth/refresh')).length, 1);
  assert.equal(expiredCount, 1);
  assert.deepEqual(client.getSession(), { accessToken: null, refreshToken: null });
});

test('public health requests do not attach a bearer token', async () => {
  const calls = [];
  const client = createApiClient({
    baseUrl: 'https://api.test',
    fetchImpl: async (url, options = {}) => {
      calls.push({ url, options });
      return mockResponse(200, { status: 'ok' });
    },
  });
  client.setSession({ access_token: 'should-not-be-sent', refresh_token: 'refresh' });

  await client.health();
  await client.healthDetailed();
  assert.equal(headerValue(calls[0].options, 'authorization'), undefined);
  assert.equal(headerValue(calls[1].options, 'authorization'), undefined);
});

test('static server serves only the public asset allow-list', async () => {
  const server = createStaticServer();
  const port = await listen(server);
  try {
    const publicResponse = await fetch(`http://127.0.0.1:${port}/index.html`);
    assert.equal(publicResponse.status, 200);
    assert.match(await publicResponse.text(), /id="auth-form"/);

    for (const path of [
      '/server.mjs',
      '/package.json',
      '/.env',
      '/%2e%2e%2fserver.mjs',
      '/frontend/app.js',
      '/index.html/secret',
    ]) {
      const response = await fetch(`http://127.0.0.1:${port}${path}`);
      assert.equal(response.status, 404, `unexpectedly served ${path}`);
    }

    const queryResponse = await fetch(`http://127.0.0.1:${port}/styles.css?cache=1`);
    assert.equal(queryResponse.status, 200);
    assert.match(queryResponse.headers.get('content-type'), /text\/css/);
  } finally {
    await close(server);
  }
});
