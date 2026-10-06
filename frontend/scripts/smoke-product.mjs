// Live production frontend + active TypeScript client + FastAPI integration.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const apiUrl = process.env.SMOKE_API_URL || 'http://localhost:8000';
const webUrl = process.env.SMOKE_WEB_URL || 'http://localhost:3000';
const source = await readFile(new URL('../lib/api-client.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } });
const { ApiClient } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
const routes = ['/', '/dashboard', '/ask', '/research', '/vulnerabilities', '/threats', '/papers', '/research-gaps', '/graph', '/timeline', '/log-analysis', '/ioc-analysis', '/evaluation', '/rag-security', '/experiments', '/documents', '/settings', '/admin'];
for (const route of routes) {
  const response = await fetch(webUrl + route);
  assert.equal(response.status, 200, route);
  assert.match(await response.text(), /CyberSecRA-X/);
}
const preflight = await fetch(apiUrl + '/chat/query', { method: 'OPTIONS', headers: { Origin: webUrl, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type' } });
assert.equal(preflight.headers.get('access-control-allow-origin'), webUrl);
const api = new ApiClient(apiUrl);
await api.register(`release-${crypto.randomUUID()}@example.test`, crypto.randomUUID() + ' password');
const workspace = (await api.createWorkspace('Live product smoke workspace')).workspace;
const answer = await api.query('What does NIST CSF 2.0 provide?', 'RESEARCHER', workspace.id);
assert.ok(answer.answer_id && answer.evidence.length && answer.claims.length);
assert.ok((await api.history()).answers.some(item => item.answer_id === answer.answer_id));
const exported = await api.exportAnswer(answer.answer_id, 'json');
assert.ok(exported.content_base64);
const uploaded = await api.upload('release-smoke.txt', Buffer.from('Defensive research evidence fixture.').toString('base64'));
const completed = await api.waitForUpload(uploaded);
assert.equal(completed.status, 'indexed');
await api.deleteDocument(uploaded.document.document_id);
const experiment = (await api.createExperiment({ name: 'Live lifecycle fixture', dataset: '', model: '', hyperparameters: {}, notes: '', status: 'created' })).experiment;
await api.updateExperiment(experiment.id, { status: 'completed' });
await api.deleteExperiment(experiment.id);
let verifiedComplete = false;
await api.streamQuery('What does NIST CSF 2.0 provide?', 'RESEARCHER', (event, data) => { if (event === 'complete') verifiedComplete = Boolean(data.answer.answer_id); });
assert.ok(verifiedComplete);
await assert.rejects(api.adminOverview(), error => error.status === 403);
await api.logout();
console.log(JSON.stringify({ status: 'passed', frontend: webUrl, api: apiUrl, routes: routes.length, checks: ['rendered production routes', 'CORS', 'active TypeScript client', 'registration', 'query', 'history', 'workspace', 'report export', 'document upload/delete', 'experiment lifecycle', 'SSE completion', 'admin isolation', 'logout'] }, null, 2));
