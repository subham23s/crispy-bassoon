'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { useAuth } from './auth-provider';
import { EmptyState, ErrorState, JsonPanel, LoadingState } from './data-state';
import type { QueryResult } from '@/types/api';

interface QueryPageProps { title: string; eyebrow: string; description: string; placeholder: string; initialQuery?: string; mode?: string; endpoint?: 'query' | 'vulnerability'; }

export function QueryPage({ title, eyebrow, description, placeholder, initialQuery = '', mode = 'RESEARCHER', endpoint = 'query' }: QueryPageProps) {
  const { api } = useAuth();
  const [input, setInput] = useState(initialQuery);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [streamText, setStreamText] = useState('');
  const [stage, setStage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const [exporting, setExporting] = useState(false);
  const [history, setHistory] = useState<QueryResult[]>([]);
  const [historyError, setHistoryError] = useState('');
  useEffect(() => {
    let active = true;
    api.history().then(value => { if (active) { setHistory(value.answers); setHistoryError(''); } }).catch(reason => { if (active) setHistoryError(reason instanceof Error ? reason.message : 'History unavailable.'); });
    return () => { active = false; };
  }, [api, result?.answer_id]);
  useEffect(() => () => controller.current?.abort(), []);
  async function download(format: string) {
    if (!result?.answer_id) return;
    setExporting(true);
    try {
      const report = await api.exportAnswer(String(result.answer_id), format);
      const bytes = Uint8Array.from(atob(report.content_base64), char => char.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: report.media_type }));
      const link = document.createElement('a'); link.href = url; link.download = report.filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Report export failed.'); }
    finally { setExporting(false); }
  }
  async function run(value = input) {
    if (!value.trim()) return;
    setLoading(true); setError(''); setResult(null); setStreamText(''); setStage('SEARCHING');
    controller.current?.abort();
    controller.current = new AbortController();
    try {
      if (endpoint === 'vulnerability') {
        setResult(await api.vulnerability(value.trim()));
      } else {
        await api.streamQuery(value.trim(), mode, (event, data) => {
          if (event === 'status') setStage(String(data.stage ?? 'STATUS'));
          if (event === 'answer_delta') setStreamText((current) => current + String(data.text ?? ''));
          if (event === 'answer_reset') setStreamText('');
          if (event === 'complete' && data.answer && typeof data.answer === 'object') setResult(data.answer as QueryResult);
        }, false, undefined, controller.current.signal);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The API request failed.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { if (initialQuery) void run(initialQuery); }, [initialQuery]); // eslint-disable-line react-hooks/exhaustive-deps
  function submit(event: FormEvent) { event.preventDefault(); void run(); }
  const evidence = Array.isArray(result?.evidence) ? result.evidence : [];
  const claims = Array.isArray(result?.claims) ? result.claims : [];
  return <section className="page"><div className="section-heading"><div><p className="eyebrow accent">{eyebrow}</p><h2>{title}</h2><p className="muted">{description}</p></div></div>
    <form className="panel" onSubmit={submit}><div className="form-row"><label><span className="label">{endpoint === 'vulnerability' ? 'CVE identifier' : 'Research question'}</span><input className="control" value={input} onChange={(event) => setInput(event.target.value)} placeholder={placeholder} /></label><button className="button primary" disabled={loading}>{loading ? `${stage || 'Analyzing'}…` : 'Fetch evidence →'}</button></div></form>
    <details className="panel"><summary>Saved answer history ({history.length})</summary>{historyError && <ErrorState message={historyError} />}{!history.length && !historyError && <p className="muted">No saved answers yet.</p>}<div className="card-list">{history.map(saved => <button className="list-item" key={saved.answer_id} disabled={loading} onClick={() => { setResult(saved); setInput(saved.query ?? ''); setError(''); }}><strong>{saved.query}</strong><p className="muted">{String(saved.created_at ?? '')} · {saved.abstained ? 'Abstained' : 'Evidence response'}</p></button>)}</div></details>
    {loading && <div className="panel"><p className="eyebrow">LIVE PIPELINE</p><p className="muted">{stage || 'Starting'} · generation is provisional until verification completes.</p>{streamText && <p className="answer">{streamText}</p>}<button className="button secondary" onClick={() => controller.current?.abort()}>Cancel</button><LoadingState label="Waiting for verified completion…" /></div>}
    {result?.answer_id && <div className="panel"><h3>Export this verified answer</h3>{['markdown', 'json', 'pdf', 'docx'].map(format => <button key={format} className="button secondary" disabled={exporting} onClick={() => void download(format)}>{format.toUpperCase()}</button>)}</div>}
    {error && <ErrorState message={error} onRetry={() => void run()} />}
    {!loading && !error && !result && <EmptyState>Submit a request to see API-backed content, citations, claims, and limitations.</EmptyState>}
    {!loading && !error && result && <div className="grid two-col"><article className="panel"><p className="eyebrow">API RESPONSE</p><h3>{result.abstained ? 'Abstained: evidence was insufficient' : result.query ?? 'Query result'}</h3><p className="answer">{result.answer ?? streamText ?? 'The API returned no narrative answer.'}</p><div className="metric-row">{result.cers && <div className="metric"><span className="muted">CERS</span><strong>{result.cers.percentage ?? '—'}%</strong></div>}<div className="metric"><span className="muted">Evidence chunks</span><strong>{evidence.length}</strong></div><div className="metric"><span className="muted">Claims</span><strong>{claims.length}</strong></div></div></article><article className="panel"><p className="eyebrow">RAW CONTRACT</p><JsonPanel value={result} /></article><article className="panel"><h3>Retrieved evidence</h3>{evidence.length ? <div className="card-list">{evidence.map((item, index) => <div className="list-item" key={String(item.id ?? index)}><header><strong>[C{index + 1}] {String(item.source ?? item.title ?? 'Source not reported')}</strong><span className="badge">retrieved</span></header><p>{String(item.text ?? item.content ?? 'No excerpt reported.')}</p>{typeof item.url === 'string' && item.url && <a href={item.url} target="_blank" rel="noreferrer">Inspect source ↗</a>}</div>)}</div> : <EmptyState>No evidence chunks were reported by the API.</EmptyState>}</article><article className="panel"><h3>Claims and limitations</h3>{claims.length ? <div className="card-list">{claims.map((claim, index) => <div className="list-item" key={index}><strong>{String(claim.status ?? 'UNSPECIFIED')}</strong><p>{String(claim.claim ?? 'Claim text not reported.')}</p></div>)}</div> : <EmptyState>No claims were reported.</EmptyState>}<h3>Limitations</h3>{Array.isArray(result.limitations) && result.limitations.length ? <ul>{result.limitations.map((item, index) => <li key={index}>{String(item)}</li>)}</ul> : <p className="muted">No limitations were reported.</p>}</article></div>}
  </section>;
}
