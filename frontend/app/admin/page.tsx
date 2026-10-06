'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/components/auth-provider';
import { ErrorState, JsonPanel, LoadingState } from '@/components/data-state';
import type { JsonRecord } from '@/types/api';

export default function AdminPage() {
  const { api } = useAuth();
  const [overview, setOverview] = useState<JsonRecord | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [job, setJob] = useState<JsonRecord | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const active = job?.status === 'QUEUED' || job?.status === 'PROCESSING';
  async function load() {
    setError(''); setLoading(true);
    try {
      const [data, choices, status] = await Promise.all([api.adminOverview(), api.refreshSources(), api.refreshStatus()]);
      setOverview(data); setSources(choices.sources);
      const jobs = Array.isArray(status.jobs) ? status.jobs as JsonRecord[] : [];
      setJob(jobs.find(item => ['QUEUED', 'PROCESSING'].includes(String(item.status))) ?? jobs.at(-1) ?? null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Administration unavailable.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [api]);
  useEffect(() => {
    if (!active || !job?.job_id) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await api.refreshJob(String(job!.job_id));
        if (cancelled) return;
        setJob(response.job);
        if (['QUEUED', 'PROCESSING'].includes(String(response.job.status))) timer = setTimeout(() => void poll(), 2000);
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Job polling failed.'); }
    }
    timer = setTimeout(() => void poll(), 1000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [api, active, job?.job_id]);
  async function start() {
    setStarting(true); setError('');
    try { setJob((await api.startRefresh(selected)).job); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Refresh failed.'); }
    finally { setStarting(false); }
  }
  return <section className="page"><div className="section-heading"><div><p className="eyebrow accent">ADMINISTRATION</p><h2>Operations and source refresh</h2><p className="muted">Inspect persisted state and refresh configured official sources.</p></div><button className="button secondary" disabled={loading} onClick={() => void load()}>Reload status</button></div>
    {loading && <LoadingState />}{error && <ErrorState message={error} />}
    {overview && <><div className="panel"><h3>Refresh official source snapshots</h3><p className="muted">Successful acquisitions rebuild the shared indexes. Source errors and partial runs are shown in the job result.</p><div className="card-list">{sources.map(source => <label key={source}><input type="checkbox" checked={selected.includes(source)} disabled={active || starting} onChange={event => setSelected(event.target.checked ? [...selected, source] : selected.filter(item => item !== source))} /> {source}</label>)}</div><button className="button primary" disabled={active || starting || !selected.length} onClick={() => void start()}>{active ? `Refresh ${String(job?.status).toLowerCase()}…` : starting ? 'Starting…' : 'Refresh selected sources'}</button>{job && <><h3>Job: {String(job.status)}</h3><JsonPanel value={job} /></>}</div><div className="panel"><h3>Repository and service overview</h3><JsonPanel value={overview} /></div></>}
  </section>;
}
