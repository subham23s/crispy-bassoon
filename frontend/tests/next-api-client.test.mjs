import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

// Execute the active Next.js client, not a second hand-written test client.
const source = await readFile(new URL('../lib/api-client.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } });
const { ApiClient, ApiError } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } });
const tokens = { access_token: 'access-old', refresh_token: 'refresh-old' };

test('Next client coalesces concurrent refreshes and persists rotated tokens', async t => {
  const sessions = []; let refreshes = 0;
  const api = new ApiClient('https://api.example.test', () => assert.fail('session expired'), session => sessions.push(session));
  api.setSession(tokens);
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++;
      await new Promise(resolve => setTimeout(resolve, 10));
      return json({ access_token: 'access-new', refresh_token: 'refresh-new' });
    }
    return options.headers.get('authorization') === 'Bearer access-new' ? json({ documents: [] }) : json({ detail: 'expired' }, 401);
  });
  await Promise.all([api.documents(), api.documents()]);
  assert.equal(refreshes, 1);
  assert.deepEqual(sessions.at(-1), { access_token: 'access-new', refresh_token: 'refresh-new' });
});

test('Next client keeps an authenticated session on admin 403', async t => {
  const api = new ApiClient('https://api.example.test', () => assert.fail('403 must not expire session'));
  api.setSession(tokens);
  t.mock.method(globalThis, 'fetch', async () => json({ detail: 'Administrator role required' }, 403));
  await assert.rejects(api.adminOverview(), error => error instanceof ApiError && error.status === 403);
  assert.equal(api.getSession().accessToken, tokens.access_token);
});

test('Next streaming handles split UTF-8, CRLF, reset, and verified completion', async t => {
  const bytes = new TextEncoder().encode('event: status\r\ndata: {"stage":"GENERATING"}\r\n\r\nevent: answer_delta\ndata: {"text":"évidence"}\n\nevent: answer_reset\ndata: {}\n\nevent: complete\ndata: {"answer":{"answer":"verified"}}\n\n');
  t.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({ start(controller) { for (const byte of bytes) controller.enqueue(new Uint8Array([byte])); controller.close(); } })));
  const events = [];
  await new ApiClient().streamQuery('security', 'RESEARCHER', (event, data) => events.push([event, data]));
  assert.equal(events[1][1].text, 'évidence');
  assert.equal(events[2][0], 'answer_reset');
  assert.equal(events.at(-1)[1].answer.answer, 'verified');
});

test('Next streaming rejects interrupted and error streams', async t => {
  for (const stream of ['event: answer_delta\ndata: {"text":"provisional"}\n\n', 'event: error\ndata: {"detail":"Verification failed"}\n\n']) {
    const mock = t.mock.method(globalThis, 'fetch', async () => new Response(stream));
    await assert.rejects(new ApiClient().streamQuery('security', 'RESEARCHER', () => {}), ApiError);
    mock.mock.restore();
  }
});

test('Next streaming refreshes once and forwards workspace and cancellation', async t => {
  const api = new ApiClient(); api.setSession(tokens);
  const abort = new AbortController(); let calls = 0;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url.endsWith('/auth/refresh')) return json({ access_token: 'access-new', refresh_token: 'refresh-new' });
    assert.equal(JSON.parse(options.body).workspace_id, 'workspace-1');
    assert.equal(options.signal, abort.signal);
    calls++;
    return calls === 1 ? json({ detail: 'expired' }, 401) : new Response('event: complete\ndata: {"answer":{}}\n\n');
  });
  await api.streamQuery('security', 'RESEARCHER', () => {}, false, 'workspace-1', abort.signal);
  assert.equal(calls, 2);
});

test('Next experiment actions send measured values and encoded resource IDs', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => { calls.push([url, options]); return json({}); });
  const api = new ApiClient('https://api.example.test'); api.setSession(tokens);
  await api.createExperiment({ name: 'Test fixture', dataset: '', model: '', hyperparameters: {}, notes: '', status: 'created' });
  await api.updateExperiment('id/1', { status: 'completed' });
  await api.recordMetric('id/1', 'fixture metric', -0.25);
  await api.deleteExperiment('id/1');
  assert.equal(calls[1][0], 'https://api.example.test/experiments/id%2F1');
  assert.equal(calls[1][1].method, 'PATCH');
  assert.deepEqual(JSON.parse(calls[2][1].body), { name: 'fixture metric', value: -0.25 });
  assert.equal(calls[3][1].method, 'DELETE');
});

test('Next upload polling preserves quarantined completion and rejects failed extraction', async t => {
  const api = new ApiClient();
  const mock = t.mock.method(globalThis, 'fetch', async () => json({ job: { status: 'COMPLETED', document_status: 'quarantined' } }));
  assert.equal((await api.waitForUpload({ job: { job_id: 'job1' } })).status, 'quarantined');
  mock.mock.restore();
  t.mock.method(globalThis, 'fetch', async () => json({ job: { status: 'FAILED', error: 'OCR unavailable' } }));
  await assert.rejects(api.waitForUpload({ job: { job_id: 'job2' } }), /OCR unavailable/);
});
