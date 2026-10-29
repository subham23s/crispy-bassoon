'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/components/auth-provider';
import { EmptyState, ErrorState, LoadingState } from '@/components/data-state';
import type { JsonRecord } from '@/types/api';

function displayDate(value: unknown): string {
  if (typeof value !== 'string' || !value) return 'Not reported';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function SourcesPage() {
  const { api } = useAuth();
  const [sources, setSources] = useState<JsonRecord[]>([]);
  const [refreshStatus, setRefreshStatus] = useState('never_run');
  const [refreshFinishedAt, setRefreshFinishedAt] = useState<string | null>(null);
  const [refreshFailures, setRefreshFailures] = useState<Array<JsonRecord | string>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const totalRecords = useMemo(() => sources.reduce((sum, source) => sum + (typeof source.records === 'number' ? source.records : 0), 0), [sources]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.sourceCoverage();
      setSources(Array.isArray(data.sources) ? data.sources : []);
      setRefreshStatus(String(data.refresh_status ?? 'never_run'));
      setRefreshFinishedAt(typeof data.refresh_finished_at === 'string' ? data.refresh_finished_at : null);
      setRefreshFailures(Array.isArray(data.refresh_failures) ? data.refresh_failures : []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Source coverage could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { void load(); }, [load, reload]);

  return <section className="page">
    <div className="section-heading">
      <div><p className="eyebrow accent">EVIDENCE PROVENANCE</p><h2>Source coverage</h2><p className="muted">See which public references are in the research corpus and when each source was last processed.</p></div>
      <button className="button secondary" disabled={loading} onClick={() => setReload(value => value + 1)}>Refresh status</button>
    </div>
    {loading && <LoadingState />}
    {error && <ErrorState message={error} onRetry={() => setReload(value => value + 1)} />}
    {!loading && !error && <>
      <div className="metric-row">
        <div className="metric"><span className="muted">Configured sources</span><strong>{sources.length}</strong></div>
        <div className="metric"><span className="muted">Source records</span><strong>{totalRecords.toLocaleString()}</strong></div>
        <div className="metric"><span className="muted">Latest source processed</span><strong>{displayDate(sources.map(source => source.processed_at).filter((value): value is string => typeof value === 'string').sort().at(-1))}</strong><small>Refresh job: {refreshStatus.replaceAll('_', ' ')}{refreshFinishedAt ? ` · ${displayDate(refreshFinishedAt)}` : ''}</small></div>
      </div>
      {refreshFailures.length > 0 && <div className="panel"><h3>Latest refresh issues</h3><p className="muted">Some sources may be unavailable or out of date. Answers only cite evidence that was successfully indexed.</p><div className="card-list">{refreshFailures.map((failure, index) => <div className="list-item" key={index}><strong>{typeof failure === 'string' ? failure : String(failure.source_key ?? failure.source ?? 'Source update')}</strong><p>{typeof failure === 'string' ? failure : String(failure.error ?? failure.status ?? 'Refresh failed.')}</p></div>)}</div></div>}
      <div className="panel"><div className="table-wrap">{sources.length ? <table><thead><tr><th>Source</th><th>Status</th><th>Records</th><th>Version</th><th>Last processed</th><th>Reference</th></tr></thead><tbody>{sources.map((source, index) => {
        const status = String(source.status ?? 'unknown');
        const failures = Array.isArray(source.failures) ? source.failures : [];
        const references = Array.isArray(source.references) ? source.references.filter((reference): reference is JsonRecord => Boolean(reference && typeof reference === 'object')) : [];
        return <tr key={`${String(source.name)}-${index}`}><td><strong>{String(source.name ?? 'Unknown source')}</strong>{failures.length > 0 && <details><summary className="muted">{failures.length} source issue{failures.length === 1 ? '' : 's'}</summary><div className="card-list">{failures.map((failure, failureIndex) => <p key={failureIndex} className="muted">{typeof failure === 'string' ? failure : `${String(failure.title ?? failure.url ?? 'Source')}: ${String(failure.error ?? 'update failed')}`}</p>)}</div></details>}</td><td><span className={`badge ${status === 'processed' ? 'good' : 'warn'}`}>{status}</span></td><td>{typeof source.records === 'number' ? source.records.toLocaleString() : '—'}</td><td>{String(source.version || '—')}</td><td>{displayDate(source.processed_at)}</td><td>{references.length ? references.map((reference, referenceIndex) => <a key={referenceIndex} className="source-link" href={String(reference.url)} target="_blank" rel="noreferrer" style={{ display: 'block' }}>{String(reference.title || 'Official source')} ↗</a>) : typeof source.url === 'string' && source.url.startsWith('https://') ? <a className="source-link" href={source.url} target="_blank" rel="noreferrer">Official source ↗</a> : '—'}</td></tr>;
      })}</tbody></table> : <EmptyState>No source records have been reported yet.</EmptyState>}</div></div>
      <p className="muted">A processed source means it was acquired and normalized successfully; it does not mean every question is answered by that source or that its content is current.</p>
    </>}
  </section>;
}
