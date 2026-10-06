'use client';

import { FormEvent, useState } from 'react';
import { useAuth } from './auth-provider';
import { ErrorState, EmptyState, JsonPanel, LoadingState } from './data-state';

type ToolKind = 'logs' | 'ioc' | 'security';
const config: Record<ToolKind, { eyebrow: string; title: string; description: string; placeholder: string }> = {
  logs: { eyebrow: 'DEFENSIVE TRIAGE', title: 'Log analysis', description: 'Send log content to the backend heuristic parser. Results are leads, not incident determinations.', placeholder: 'Paste TXT, CSV, or JSON logs…' },
  ioc: { eyebrow: 'INDICATOR TRIAGE', title: 'IOC analysis', description: 'Classify supplied indicators through the existing backend contract without claiming maliciousness.', placeholder: 'Paste an IP, domain, URL, or hash…' },
  security: { eyebrow: 'RAG SECURITY LAB', title: 'RAG security scan', description: 'Scan document content for known prompt-injection signals before it reaches retrieval.', placeholder: 'Paste a document excerpt…' },
};
export function ToolPage({ kind }: { kind: ToolKind }) {
  const { api } = useAuth(); const copy = config[kind]; const [content, setContent] = useState(''); const [result, setResult] = useState<unknown>(null); const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  async function submit(event: FormEvent) { event.preventDefault(); if (!content.trim()) return; setLoading(true); setError(''); try { const value = kind === 'logs' ? await api.logs(content) : kind === 'ioc' ? await api.ioc(content) : await api.ragScan(content); setResult(value); } catch (reason) { setError(reason instanceof Error ? reason.message : 'The API request failed.'); } finally { setLoading(false); } }
  return <section className="page"><div className="section-heading"><div><p className="eyebrow accent">{copy.eyebrow}</p><h2>{copy.title}</h2><p className="muted">{copy.description}</p></div></div><div className="grid two-col"><form className="panel" onSubmit={submit}><label className="label" htmlFor={`${kind}-content`}>Content to analyze</label><textarea id={`${kind}-content`} value={content} onChange={(event) => setContent(event.target.value)} placeholder={copy.placeholder} rows={13} /><button className="button primary" disabled={loading}>{loading ? 'Analyzing…' : 'Run API analysis →'}</button></form><div className="panel"><p className="eyebrow">RESULT</p>{loading && <LoadingState />}{error && <ErrorState message={error} />}{!loading && !error && result === null && <EmptyState>Results appear here after the API processes supplied content.</EmptyState>}{!loading && !error && result !== null && <JsonPanel value={result} />}</div></div></section>;
}
