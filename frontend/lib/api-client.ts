import type {
  AuthResponse,
  DocumentsResponse,
  GapResponse,
  Health,
  JsonRecord,
  QueryResult,
  SourceCoverageResponse,
  User,
  ExperimentInput,
  ExperimentRecord,
  ExperimentMetric,
} from '@/types/api';

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

type RequestOptions = Omit<RequestInit, 'body'> & { body?: unknown; auth?: boolean; expireSession?: boolean };
type ExpiredHandler = () => void;

function getMessage(body: unknown, status: number): string {
  if (typeof body === 'string' && body.trim()) return body;
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && 'message' in detail) return String((detail as { message: unknown }).message);
  }
  return `Request failed (${status})`;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return {};
  const text = await response.text();
  if (!text) return {};
  try { return JSON.parse(text); } catch { return text; }
}

export class ApiClient {
  private readonly baseUrl: string;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private expiredHandler: ExpiredHandler;
  private sessionChanged: (tokens: { access_token: string; refresh_token: string } | null) => void;
  private notifying = false;
  private refreshInFlight: Promise<AuthResponse> | null = null;

  constructor(baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000', onSessionExpired: ExpiredHandler = () => {}, onSessionChanged: (tokens: { access_token: string; refresh_token: string } | null) => void = () => {}) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.expiredHandler = onSessionExpired;
    this.sessionChanged = onSessionChanged;
  }

  setSession(tokens: Partial<AuthResponse> | null): void {
    this.accessToken = tokens?.access_token ?? null;
    this.refreshToken = tokens?.refresh_token ?? null;
    this.notifying = false;
    if (this.accessToken && this.refreshToken) this.sessionChanged({ access_token: this.accessToken, refresh_token: this.refreshToken });
  }

  getSession(): { accessToken: string | null; refreshToken: string | null } {
    return { accessToken: this.accessToken, refreshToken: this.refreshToken };
  }

  clearSession(): void {
    this.accessToken = null;
    this.refreshToken = null;
    this.sessionChanged(null);
  }

  private notifyExpired(): void {
    this.clearSession();
    if (!this.notifying) {
      this.notifying = true;
      this.expiredHandler();
    }
  }

  async request<T = JsonRecord>(path: string, options: RequestOptions = {}, allowRefresh = true): Promise<T> {
    const { auth = true, expireSession = true, body, ...init } = options;
    const headers = new Headers(init.headers);
    if (body !== undefined && !headers.has('content-type')) headers.set('content-type', 'application/json');
    if (auth && this.accessToken) headers.set('authorization', `Bearer ${this.accessToken}`);
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
      headers,
    });
    const result = await parseBody(response);
    if (response.ok) return result as T;
    if (response.status === 401 && auth && allowRefresh && this.refreshToken && path !== '/auth/refresh') {
      try {
        await this.refresh();
        return this.request<T>(path, options, false);
      } catch (error) {
        this.notifyExpired();
        throw error;
      }
    }
    if (response.status === 401 && auth && expireSession) this.notifyExpired();
    throw new ApiError(getMessage(result, response.status), response.status, result);
  }

  async refresh(): Promise<AuthResponse> {
    if (this.refreshInFlight) return this.refreshInFlight;
    if (!this.refreshToken) throw new ApiError('No refresh token is available.', 401);
    this.refreshInFlight = this.request<AuthResponse>('/auth/refresh', {
      method: 'POST', auth: false, body: { refresh_token: this.refreshToken },
    }, false).then(tokens => { this.setSession(tokens); return tokens; });
    try { return await this.refreshInFlight; }
    finally { this.refreshInFlight = null; }
  }

  login(email: string, password: string): Promise<AuthResponse> {
    return this.request<AuthResponse>('/auth/login', { method: 'POST', auth: false, body: { email, password } }).then((result) => { this.setSession(result); return result; });
  }

  register(email: string, password: string): Promise<AuthResponse> {
    return this.request<AuthResponse>('/auth/register', { method: 'POST', auth: false, body: { email, password } }).then((result) => { this.setSession(result); return result; });
  }

  me(signal?: AbortSignal): Promise<{ user: User }> { return this.request('/auth/me', { signal }); }
  health(): Promise<Health> { return this.request('/health', { auth: false }); }
  healthDetailed(): Promise<Health> { return this.request('/health/detailed', { auth: false }); }
  query(query: string, mode = 'RESEARCHER', workspace_id?: string): Promise<QueryResult> { return this.request('/chat/query', { method: 'POST', body: { query, mode, ...(workspace_id ? { workspace_id } : {}) } }); }
  documents(): Promise<DocumentsResponse> { return this.request('/documents'); }
  upload(filename: string, content_base64: string, source_type = 'user_document'): Promise<JsonRecord> { return this.request('/documents/upload', { method: 'POST', body: { filename, content_base64, source_type } }); }
  documentJob(id: string): Promise<{ job: JsonRecord }> { return this.request(`/documents/jobs/${encodeURIComponent(id)}`); }
  async waitForUpload(result: JsonRecord, onStatus: (status: string) => void = () => {}): Promise<JsonRecord> {
    const job = result.job as JsonRecord | undefined;
    if (!job?.job_id) return result;
    for (let attempt = 0; attempt < 300; attempt++) {
      const { job: current } = await this.documentJob(String(job.job_id));
      onStatus(String(current.status));
      if (current.status === 'FAILED') throw new ApiError(String(current.error || 'Document processing failed'), 400);
      if (current.status === 'COMPLETED') return { ...result, status: current.document_status, job: current };
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    throw new ApiError('Processing is still queued. Check the document library for its status.', 408);
  }
  deleteDocument(id: string): Promise<JsonRecord> { return this.request(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }); }
  logs(content: string): Promise<JsonRecord> { return this.request('/logs/analyze', { method: 'POST', body: { content } }); }
  ioc(content: string): Promise<JsonRecord> { return this.request('/ioc/analyze', { method: 'POST', body: { content } }); }
  ragScan(content: string): Promise<JsonRecord> { return this.request('/rag-security/scan', { method: 'POST', body: { content } }); }
  gapAnalysis(): Promise<GapResponse> { return this.request('/research/gap-analysis', { method: 'POST', body: {} }); }
  vulnerability(cve: string): Promise<QueryResult> { return this.request(`/vulnerabilities/${encodeURIComponent(cve)}`); }
  graph(entity: string): Promise<JsonRecord> { return this.request(`/graph/entity/${encodeURIComponent(entity)}`); }
  papers(): Promise<JsonRecord> { return this.request('/papers'); }
  analyzePaper(document_id: string): Promise<JsonRecord> { return this.request('/papers/analyze', { method: 'POST', body: { document_id } }); }
  comparePapers(document_ids: string[]): Promise<JsonRecord> { return this.request('/papers/compare', { method: 'POST', body: { document_ids } }); }
  history(): Promise<{ answers: QueryResult[] }> { return this.request('/chat/history'); }
  exportAnswer(answer_id: string, format: string): Promise<{ filename: string; media_type: string; content_base64: string }> { return this.request('/reports/export', { method: 'POST', body: { answer_id, format } }); }
  vulnerabilities(): Promise<JsonRecord> { return this.request('/vulnerabilities'); }
  threats(): Promise<JsonRecord> { return this.request('/threats'); }
  timeline(start?: string, end?: string): Promise<JsonRecord> { const params = new URLSearchParams(); if (start) params.set('start', start); if (end) params.set('end', end); return this.request(`/timeline${params.toString() ? `?${params.toString()}` : ''}`); }
  evaluation(): Promise<JsonRecord> { return this.request('/evaluation'); }
  ragSecurityEvaluation(): Promise<JsonRecord> { return this.request('/rag-security/evaluate'); }
  experiments(): Promise<JsonRecord> { return this.request('/experiments'); }
  compareExperiments(): Promise<{ experiments: ExperimentRecord[] }> { return this.request('/experiments/compare'); }
  createExperiment(input: ExperimentInput): Promise<{ experiment: ExperimentRecord }> { return this.request('/experiments', { method: 'POST', body: input }); }
  updateExperiment(id: string, input: Partial<ExperimentInput>): Promise<{ experiment: ExperimentRecord }> { return this.request(`/experiments/${encodeURIComponent(id)}`, { method: 'PATCH', body: input }); }
  deleteExperiment(id: string): Promise<JsonRecord> { return this.request(`/experiments/${encodeURIComponent(id)}`, { method: 'DELETE' }); }
  recordMetric(id: string, name: string, value: number): Promise<{ metrics: ExperimentMetric[] }> { return this.request(`/experiments/${encodeURIComponent(id)}/metrics`, { method: 'POST', body: { name, value } }); }
  workspaces(): Promise<JsonRecord> { return this.request('/research/workspaces'); }
  createWorkspace(name: string): Promise<JsonRecord> { return this.request('/research/workspaces', { method: 'POST', body: { name } }); }
  workspaceItems(id: string): Promise<JsonRecord> { return this.request(`/research/workspaces/${encodeURIComponent(id)}/items`); }
  workspaceNotes(id: string): Promise<JsonRecord> { return this.request(`/research/workspaces/${encodeURIComponent(id)}/notes`); }
  createWorkspaceItem(id: string, title: string, item_type = 'question'): Promise<JsonRecord> { return this.request(`/research/workspaces/${encodeURIComponent(id)}/items`, { method: 'POST', body: { title, item_type } }); }
  createNote(id: string, body: string, title = ''): Promise<JsonRecord> { return this.request(`/research/workspaces/${encodeURIComponent(id)}/notes`, { method: 'POST', body: { title, body } }); }
  workspaceEvidence(id: string): Promise<JsonRecord> { return this.request(`/research/workspaces/${encodeURIComponent(id)}/evidence`); }
  saveEvidence(id: string, evidence_id: string, note = ''): Promise<JsonRecord> { return this.request(`/research/workspaces/${encodeURIComponent(id)}/evidence`, { method: 'POST', body: { evidence_id, note } }); }
  adminOverview(): Promise<JsonRecord> { return this.request('/admin/overview'); }
  refreshStatus(): Promise<JsonRecord> { return this.request('/data/refresh/status'); }
  sourceCoverage(): Promise<SourceCoverageResponse> { return this.request('/data/sources'); }
  refreshSources(): Promise<{ sources: string[] }> { return this.request('/data/refresh/sources'); }
  startRefresh(sources: string[], force = false): Promise<{ job: JsonRecord }> { return this.request('/data/refresh', { method: 'POST', body: { sources, force } }); }
  refreshJob(id: string): Promise<{ job: JsonRecord }> { return this.request(`/data/refresh/jobs/${encodeURIComponent(id)}`); }
  async streamQuery(query: string, mode = 'RESEARCHER', onEvent: (event: string, data: JsonRecord) => void, retried = false, workspace_id?: string, signal?: AbortSignal, answerStyle = 'balanced'): Promise<void> {
    const response = await fetch(`${this.baseUrl}/chat/stream`, { method: 'POST', signal, headers: { accept: 'text/event-stream', 'content-type': 'application/json', ...(this.accessToken ? { authorization: `Bearer ${this.accessToken}` } : {}) }, body: JSON.stringify({ query, mode, answer_style: answerStyle, ...(workspace_id ? { workspace_id } : {}) }) });
    if (response.status === 401 && !retried && this.refreshToken) {
      await response.body?.cancel();
      try { await this.refresh(); } catch (error) { this.notifyExpired(); throw error; }
      return this.streamQuery(query, mode, onEvent, true, workspace_id, signal, answerStyle);
    }
    if (response.status === 401) this.notifyExpired();
    if (!response.ok || !response.body) throw new ApiError(getMessage(await parseBody(response), response.status), response.status);
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let completed = false;
    try {
      while (!completed) {
        const read = await reader.read();
        buffer += read.done ? decoder.decode() : decoder.decode(read.value, { stream: true });
        const frames = buffer.split(/\r?\n\r?\n/); buffer = frames.pop() ?? '';
        for (const raw of frames) {
          const lines = raw.split(/\r?\n/);
          const event = lines.find(line => line.startsWith('event:'))?.slice(6).trim() ?? 'message';
          const dataLines = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).replace(/^ /, ''));
          if (!dataLines.length) continue;
          const data = JSON.parse(dataLines.join('\n')) as JsonRecord;
          if (event === 'error') throw new ApiError(String(data.detail || 'Streaming query failed'), 500, data);
          onEvent(event, data);
          if (event === 'complete') { completed = true; break; }
        }
        if (read.done) break;
      }
      if (!completed) throw new ApiError('The stream ended before verification completed. Please retry.', 502);
    } finally { await reader.cancel(); reader.releaseLock(); }
  }
  async logout(): Promise<JsonRecord> {
    try {
      try { return await this.request('/auth/logout', { method: 'POST', expireSession: false, body: { refresh_token: this.refreshToken } }, false); }
      catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401 || !this.refreshToken) throw error;
        await this.refresh();
        return await this.request('/auth/logout', { method: 'POST', expireSession: false, body: { refresh_token: this.refreshToken } }, false);
      }
    } finally { this.clearSession(); }
  }
}
