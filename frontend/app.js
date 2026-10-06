import { createApiClient } from './api-client.mjs';

const API = window.CYBERSEC_API_URL || 'http://localhost:8000';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {
  authMode: 'login',
  user: null,
  health: null,
  detailedHealth: null,
};
let toastTimer;

const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  "'": '&#39;',
  '"': '&quot;',
}[character]));

function displayValue(value) {
  if (value === null || value === undefined || value === '') return 'not reported';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function formatPercent(value, missingLabel = 'not reported') {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return missingLabel;
  return `${(Number(value) * 100).toFixed(0)}%`;
}

function toast(message) {
  const node = $('#toast');
  if (!node) return;
  node.textContent = message;
  node.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove('show'), 3500);
}

function showView(view) {
  if (!state.user) return;
  $$('.view').forEach((node) => node.classList.toggle('active', node.id === `view-${view}`));
  $$('.nav-item').forEach((node) => node.classList.toggle('active', node.dataset.view === view));
  const titles = {
    dashboard: 'Good evening, researcher.',
    ask: 'Evidence console',
    investigate: 'Investigation desk',
    research: 'Research intelligence',
    documents: 'Document library',
    security: 'RAG security lab',
  };
  $('#page-title').textContent = titles[view] || 'CyberSecRA-X';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setAuthMessage(message, isError = false) {
  const node = $('#auth-message');
  node.textContent = message;
  node.classList.toggle('error', isError);
}

function setAuthenticated(user) {
  state.user = user || null;
  const authenticated = Boolean(state.user);
  document.body.classList.toggle('authenticated', authenticated);
  $('#auth-panel').hidden = authenticated;
  $('#app-content').hidden = !authenticated;
  $('#user-email').textContent = authenticated ? state.user.email || '' : '';
  $('#auth-user-state').textContent = authenticated ? 'Signed in' : '—';
  if (authenticated) {
    setAuthMessage('');
    loadDocuments();
  }
}

function handleSessionExpired() {
  if (!state.user) return;
  setAuthenticated(null);
  setAuthMessage('Your session expired. Sign in again to continue.', true);
  toast('Your session expired. Please sign in again.');
}

const apiClient = createApiClient({
  baseUrl: API,
  fetchImpl: (...args) => window.fetch(...args),
  onSessionExpired: handleSessionExpired,
});

function setHealthDot(selector, healthy) {
  const dot = $(selector);
  if (!dot) return;
  dot.classList.toggle('amber', !healthy);
  dot.classList.toggle('danger', healthy === false && state.health?.status === 'error');
}

function prettyLabel(value) {
  return String(value).replace(/[_-]+/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

function renderHealth() {
  const health = state.health || {};
  const detailed = state.detailedHealth || {};
  const healthy = health.status === 'ok';
  const statusText = health.status ? prettyLabel(health.status) : 'Unavailable';
  $('#api-status').textContent = statusText;
  $('#auth-api-status').textContent = health.status ? `Public API: ${statusText}` : 'Public API health unavailable';
  $('#sidebar-health').textContent = health.status ? `API health: ${statusText}` : 'API health unavailable';
  $('#health-badge').textContent = statusText;
  $('#health-badge').classList.toggle('success', healthy);
  $('#health-badge').classList.toggle('warning', !healthy);
  setHealthDot('#api-health-dot', healthy);
  setHealthDot('#auth-health-dot', healthy);
  setHealthDot('#sidebar-health-dot', healthy);

  $('#health-runtime').textContent = displayValue(detailed.runtime || health.runtime);
  $('#health-runtime-detail').textContent = detailed.runtime ? 'reported by /health/detailed' : 'runtime not reported';
  const capabilitySource = detailed.capabilities && typeof detailed.capabilities === 'object'
    ? detailed.capabilities
    : Object.fromEntries(Object.entries(detailed).filter(([key]) => key !== 'status'));
  const entries = Array.isArray(capabilitySource)
    ? capabilitySource.map((value, index) => [`capability_${index + 1}`, value])
    : Object.entries(capabilitySource);
  const capabilityNode = $('#health-capabilities');
  capabilityNode.innerHTML = entries.length
    ? entries.map(([key, value]) => `<div><span>${escapeHtml(prettyLabel(key))}</span><b>${escapeHtml(displayValue(value))}</b></div>`).join('')
    : '<p class="muted">The API did not report detailed capabilities.</p>';
  const evidenceMode = health.evidence_mode;
  $('#health-note').textContent = evidenceMode
    ? `Evidence mode reported by the API: ${evidenceMode}.`
    : healthy
      ? 'The API is responding; no evidence mode was reported.'
      : 'The API health response is unavailable. No capability is assumed.';
}

async function checkApi() {
  const [healthResult, detailedResult] = await Promise.allSettled([apiClient.health(), apiClient.healthDetailed()]);
  state.health = healthResult.status === 'fulfilled' ? healthResult.value : { status: 'unavailable' };
  state.detailedHealth = detailedResult.status === 'fulfilled' ? detailedResult.value : {};
  renderHealth();
}

function setAuthMode(mode) {
  state.authMode = mode;
  const registering = mode === 'register';
  $('#auth-title').textContent = registering ? 'Create your research workspace' : 'Sign in to your research workspace';
  $('#auth-submit').innerHTML = registering ? 'Create account <span aria-hidden="true">→</span>' : 'Sign in <span aria-hidden="true">→</span>';
  $('#auth-switch-prompt').textContent = registering ? 'Already have an account?' : 'Need an account?';
  $('#auth-switch').textContent = registering ? 'Sign in' : 'Register';
  $('#confirm-password-row').hidden = !registering;
  $('#auth-password').autocomplete = registering ? 'new-password' : 'current-password';
  $('#auth-confirm-password').required = registering;
  setAuthMessage('');
}

async function submitAuth(event) {
  event.preventDefault();
  const email = $('#auth-email').value.trim();
  const password = $('#auth-password').value;
  if (!email || !password) return setAuthMessage('Email and password are required.', true);
  if (state.authMode === 'register' && password !== $('#auth-confirm-password').value) {
    return setAuthMessage('Passwords do not match.', true);
  }

  const button = $('#auth-submit');
  button.disabled = true;
  button.textContent = state.authMode === 'register' ? 'Creating account…' : 'Signing in…';
  setAuthMessage('');
  try {
    const result = state.authMode === 'register'
      ? await apiClient.register(email, password)
      : await apiClient.login(email, password);
    const profile = await apiClient.me();
    setAuthenticated(profile.user || (profile.email ? profile : null) || result.user || { email });
    showView('dashboard');
    toast(state.authMode === 'register' ? 'Account created.' : 'Signed in.');
  } catch (error) {
    setAuthMessage(error.message || 'Authentication failed.', true);
  } finally {
    button.disabled = false;
    button.innerHTML = state.authMode === 'register'
      ? 'Create account <span aria-hidden="true">→</span>'
      : 'Sign in <span aria-hidden="true">→</span>';
  }
}

async function signOut() {
  const button = $('#logout-button');
  button.disabled = true;
  try {
    await apiClient.logout();
    toast('Signed out.');
  } catch (error) {
    toast(`Sign out completed locally: ${error.message}`);
  } finally {
    setAuthenticated(null);
    setAuthMode('login');
    $('#auth-email').value = '';
    $('#auth-password').value = '';
    $('#auth-confirm-password').value = '';
    button.disabled = false;
  }
}

function isHttpUrl(value) {
  try {
    const parsed = new URL(String(value));
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

function renderCitation(url) {
  if (isHttpUrl(url)) return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Inspect source ↗</a>`;
  return '<span class="citation-unavailable">Source URL not provided as a valid HTTP(S) citation.</span>';
}

function renderList(items, emptyMessage) {
  if (!Array.isArray(items) || !items.length) return `<p class="muted">${escapeHtml(emptyMessage)}</p>`;
  return `<ul class="metadata-list">${items.map((item) => `<li>${escapeHtml(typeof item === 'object' ? displayValue(item) : item)}</li>`).join('')}</ul>`;
}

function renderAnswer(result) {
  const cers = result.cers && result.cers.percentage !== undefined && result.cers.percentage !== null ? Number(result.cers.percentage) : null;
  const claims = Array.isArray(result.claims) ? result.claims.map((claim) => {
    const status = String(claim.status || 'UNSPECIFIED');
    const statusClass = status === 'SUPPORTED' ? 'good' : status === 'UNSUPPORTED' ? 'warn' : 'caution';
    const score = formatPercent(claim.support_score, 'not scored');
    const citations = Array.isArray(claim.citation_ids) && claim.citation_ids.length ? ` Citations: ${claim.citation_ids.join(', ')}.` : ' No verified citation ID reported.';
    return `<div class="claim"><b class="${statusClass}">${escapeHtml(status)} · ${escapeHtml(score)}</b><span>${escapeHtml(claim.claim || 'Claim text not reported')}</span><small>${escapeHtml(claim.explanation || 'No explanation reported.')}${escapeHtml(citations)}</small></div>`;
  }).join('') : '';
  const evidenceItems = Array.isArray(result.evidence) ? result.evidence : [];
  const evidence = evidenceItems.length
    ? evidenceItems.map((item, index) => `<article class="evidence-item"><header><b>[C${index + 1}] Retrieved source: ${escapeHtml(item.source || item.title || 'Unnamed source')}</b><span>authority ${escapeHtml(formatPercent(item.authority_score))}</span></header><p class="evidence-label">Retrieved excerpt · context only; not independently verified</p><p>${escapeHtml(item.text || item.content || 'No excerpt reported.')}</p>${renderCitation(item.url)}</article>`).join('')
    : '<p class="muted">No evidence was retrieved by the API for this response.</p>';
  const conflicts = result.conflicts || [];
  const limitations = result.limitations || [];
  const agentPlan = result.agent_plan || result.metadata?.agent_plan;
  const relatedEntities = result.related_entities || [];
  const timeline = result.timeline || [];
  const answerLabel = result.abstained ? 'ABSTAINED · insufficient support' : 'RESPONSE · verify before relying';
  const cersText = Number.isFinite(cers) ? `${Math.max(0, Math.min(100, cers)).toFixed(1)}%` : '—';

  $('#cers-value').textContent = cersText;
  $('#cers-detail').textContent = result.abstained ? 'Latest response abstained' : 'Reported by latest response';
  $('#answer-output').classList.remove('empty-state');
  $('#answer-output').innerHTML = `<div class="answer-card"><div class="answer-main"><span class="eyebrow">${escapeHtml(answerLabel)}</span><h3>${escapeHtml(result.query || 'Query result')}</h3><div class="answer-text">${escapeHtml(result.answer || 'The API did not provide an answer.')}</div><div class="section-head compact"><div><span class="eyebrow">SOURCES &amp; PROVENANCE</span><h3>${evidenceItems.length} retrieved evidence chunk${evidenceItems.length === 1 ? '' : 's'}</h3></div></div><div class="evidence-list">${evidence}</div><div class="metadata-block"><h3>Reported conflicts</h3>${renderList(conflicts, 'No conflicts were reported by the API.')}</div><div class="metadata-block"><h3>Limitations</h3>${renderList(limitations, 'No limitations were reported by the API.')}</div>${agentPlan ? `<div class="metadata-block"><h3>Agent plan metadata</h3><p class="caution">${escapeHtml(displayValue(agentPlan))}</p><small class="muted">Metadata reported by the API; it is not evidence.</small></div>` : ''}</div><aside class="answer-side"><span class="eyebrow">CYBER EVIDENCE RELIABILITY</span><div class="metric"><span>CERS</span><strong>${escapeHtml(cersText)}</strong></div><div class="meter"><span style="width:${Number.isFinite(cers) ? Math.min(100, Math.max(0, cers)) : 0}%"></span></div><p class="muted metric-note">Project-defined signal, not a probability of truth.</p><div class="metric"><span>Intent</span><strong>${escapeHtml(result.understanding?.intent || 'not reported')}</strong></div><div class="metric"><span>Complexity</span><strong>${escapeHtml(result.understanding?.complexity || 'not reported')}</strong></div><div class="section-head compact"><div><span class="eyebrow">CLAIM VERIFICATION</span></div></div>${claims || '<p class="muted">No claims were reported by the API.</p>'}<div class="metadata-block"><h3>Related entities</h3>${renderList(relatedEntities, 'No related entities were reported.')}</div><div class="metadata-block"><h3>Timeline metadata</h3>${renderList(timeline, 'No timeline metadata was reported.')}</div></aside></div>`;
}

async function ask() {
  const query = $('#query-input').value.trim();
  if (!query) return toast('Enter a question first.');
  const button = $('#ask-button');
  button.disabled = true;
  button.textContent = 'Checking evidence…';
  try {
    renderAnswer(await apiClient.request('/chat/query', {
      method: 'POST',
      body: JSON.stringify({ query, mode: $('#answer-mode').value }),
    }));
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Analyze evidence <span aria-hidden="true">→</span>';
  }
}

async function investigateCve() {
  const cve = $('#cve-input').value.trim();
  if (!cve) return toast('Enter a CVE identifier.');
  showView('ask');
  $('#query-input').value = `Investigate ${cve}: what is known, what evidence supports it, and what remains unknown?`;
  await ask();
}

async function toolPost(path, inputSelector, outputSelector) {
  const content = $(inputSelector).value.trim();
  if (!content) return toast('Provide content to analyze.');
  try {
    const result = await apiClient.request(path, { method: 'POST', body: JSON.stringify({ content }) });
    $(outputSelector).textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    toast(error.message);
  }
}

async function loadDocuments() {
  if (!state.user) return;
  try {
    const result = await apiClient.request('/documents');
    const documents = Array.isArray(result.documents) ? result.documents : [];
    $('#doc-count').textContent = documents.length;
    $('#document-table').innerHTML = documents.length ? documents.map((doc) => `<tr><td><strong>${escapeHtml(doc.title || 'Untitled document')}</strong><br><small class="muted">${escapeHtml(doc.document_id || 'ID not reported')}</small></td><td>${escapeHtml(doc.source || 'not reported')}</td><td><span class="badge ${doc.status === 'indexed' ? 'success' : 'warning'}">${escapeHtml(doc.status || 'not reported')}</span></td><td>${escapeHtml(doc.chunk_count === undefined ? 'not reported' : doc.chunk_count)}</td><td>${escapeHtml(doc.ingestion_timestamp || 'not reported')}</td><td><button type="button" class="link-button delete-document" data-document-id="${escapeHtml(doc.document_id || '')}" aria-label="Delete ${escapeHtml(doc.title || 'document')}">Delete</button></td></tr>`).join('') : '<tr><td colspan="6" class="muted">No documents are in this workspace.</td></tr>';
    $$('.delete-document').forEach((button) => button.addEventListener('click', () => deleteDocument(button.dataset.documentId)));
  } catch (error) {
    $('#doc-count').textContent = '—';
    $('#document-table').innerHTML = `<tr><td colspan="6" class="muted">Unable to load documents: ${escapeHtml(error.message)}</td></tr>`;
  }
}

async function deleteDocument(documentId) {
  if (!documentId || !window.confirm('Delete this document from the current workspace?')) return;
  try {
    await apiClient.request(`/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' });
    toast('Document deleted.');
    await loadDocuments();
  } catch (error) {
    toast(error.message);
  }
}

async function uploadDocument(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    const chunkSize = 0x8000;
    for (let index = 0; index < bytes.length; index += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
    }
    const result = await apiClient.request('/documents/upload', {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content_base64: btoa(binary) }),
    });
    const status = result.status || result.document?.status || 'not reported';
    const chunks = result.chunks === undefined ? '' : ` ${result.chunks} chunk${Number(result.chunks) === 1 ? '' : 's'}.`;
    toast(status === 'quarantined' ? `${file.name} was quarantined.${chunks}` : `${file.name}: ${status}.${chunks}`);
    await loadDocuments();
  } catch (error) {
    toast(error.message);
  }
}

async function runSecurityScan() {
  const content = $('#security-input').value.trim();
  if (!content) return toast('Provide document content.');
  try {
    const result = await apiClient.request('/rag-security/scan', { method: 'POST', body: JSON.stringify({ content }) });
    const detected = result.prompt_injection_detected === true;
    $('#security-output').innerHTML = `<span class="eyebrow">RESULT</span><h3 class="${detected ? 'warn' : 'good'}">${detected ? 'Signal detected · isolate content' : 'No known pattern detected'}</h3><p class="muted">A detection signal is not proof of intent or compromise.</p><pre class="tool-output">${escapeHtml(JSON.stringify(result, null, 2))}</pre>`;
  } catch (error) {
    toast(error.message);
  }
}

async function runGapAnalysis() {
  try {
    const result = await apiClient.request('/research/gap-analysis', { method: 'POST', body: JSON.stringify({}) });
    $('#gap-output').innerHTML = `<span class="eyebrow">OUTPUT</span><h3>Candidate research gaps</h3><p class="muted">Observations over the supplied corpus, not validated discoveries.</p><pre class="tool-output">${escapeHtml(JSON.stringify(result, null, 2))}</pre>`;
  } catch (error) {
    toast(error.message);
  }
}

function bindEvents() {
  $$('.nav-item').forEach((button) => button.addEventListener('click', () => showView(button.dataset.view)));
  $$('[data-view-target]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.viewTarget)));
  $$('[data-investigation]').forEach((button) => button.addEventListener('click', () => {
    showView('investigate');
    $('#cve-input').value = button.dataset.investigation;
    investigateCve();
  }));
  $('#theme-toggle').addEventListener('click', () => {
    const light = document.body.classList.toggle('light');
    $('#theme-toggle').setAttribute('aria-pressed', String(light));
    $('#theme-toggle').setAttribute('aria-label', light ? 'Switch to dark theme' : 'Switch to light theme');
    $('#theme-toggle').title = light ? 'Switch to dark theme' : 'Switch to light theme';
  });
  $('#auth-form').addEventListener('submit', submitAuth);
  $('#auth-switch').addEventListener('click', () => setAuthMode(state.authMode === 'login' ? 'register' : 'login'));
  $('#logout-button').addEventListener('click', signOut);
  $('#ask-button').addEventListener('click', ask);
  $('#query-input').addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') ask();
  });
  $('#cve-button').addEventListener('click', investigateCve);
  $('#log-button').addEventListener('click', () => toolPost('/logs/analyze', '#log-input', '#log-output'));
  $('#ioc-button').addEventListener('click', () => toolPost('/ioc/analyze', '#ioc-input', '#ioc-output'));
  $('#security-button').addEventListener('click', runSecurityScan);
  $('#gap-button').addEventListener('click', runGapAnalysis);
  $('#file-input').addEventListener('change', uploadDocument);
}

bindEvents();
setAuthMode('login');
checkApi();
