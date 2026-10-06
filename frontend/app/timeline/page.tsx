'use client';

import { useState } from 'react';
import { useAuth } from '@/components/auth-provider';
import { EmptyState, ErrorState, LoadingState } from '@/components/data-state';

export default function TimelinePage() {
  const { api } = useAuth();
  const [start, setStart] = useState(''); const [end, setEnd] = useState('');
  const [events, setEvents] = useState<Record<string, unknown>[]>([]); const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  async function load() { setLoading(true); setError(''); try { const response = await api.timeline(start || undefined, end || undefined); setEvents(Array.isArray(response.events) ? response.events as Record<string, unknown>[] : []); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Timeline request failed.'); } finally { setLoading(false); } }
  return <section className="page"><div className="section-heading"><div><p className="eyebrow accent">TEMPORAL EVIDENCE</p><h2>Timeline</h2><p className="muted">Publication, modification, and source-refresh events from stored metadata.</p></div></div><div className="panel"><div className="form-row"><label><span className="label">Start date</span><input type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label><label><span className="label">End date</span><input type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label><button className="button primary" onClick={() => void load()}>Apply filter</button></div></div>{loading && <LoadingState label="Loading temporal evidence…" />}{error && <ErrorState message={error} onRetry={() => void load()} />}{!loading && !error && !events.length && <EmptyState>No dated source events were returned for this filter.</EmptyState>}{!loading && !error && !!events.length && <div className="panel"><div className="table-wrap"><table><thead><tr><th>Date</th><th>Event</th><th>Title</th><th>Source</th><th>Provenance</th></tr></thead><tbody>{events.map((event, index) => <tr key={`${String(event.document_id ?? event.title)}-${index}`}><td>{String(event.date ?? '—')}</td><td>{String(event.event_type ?? '—')}</td><td>{String(event.title ?? '—')}</td><td>{String(event.source ?? '—')}</td><td>{String(event.provenance ?? '—')}</td></tr>)}</tbody></table></div></div>}</section>;
}
