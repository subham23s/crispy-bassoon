'use client';

import { ChangeEvent, useCallback, useEffect, useState } from 'react';
import { useAuth } from './auth-provider';
import { EmptyState, ErrorState, JsonPanel, LoadingState } from './data-state';
import type { JsonRecord } from '@/types/api';

export function PaperWorkspace() {
  const { api } = useAuth();
  const [papers, setPapers] = useState<JsonRecord[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<JsonRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const load = useCallback(async () => {
    const value = await api.papers();
    setPapers(Array.isArray(value.papers) ? value.papers as JsonRecord[] : []);
  }, [api]);
  useEffect(() => { load().catch(reason => setError(String(reason))); }, [load]);
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file) return;
    setBusy(true); setError(''); setStatus('Uploading paper…');
    try {
      const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
      for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
      const result = await api.waitForUpload(await api.upload(file.name, btoa(binary), 'paper'), setStatus);
      setStatus(`Paper processing: ${String(result.status)}`);
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Upload failed'); }
    finally { setBusy(false); }
  }
  async function analyze() {
    if (!selected.length) return;
    setBusy(true); setError('');
    try { setAnalysis(selected.length === 1 ? await api.analyzePaper(selected[0]) : await api.comparePapers(selected)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Paper analysis failed'); }
    finally { setBusy(false); }
  }
  return <section className="page">
    <div className="section-heading"><div><p className="eyebrow accent">LITERATURE INTELLIGENCE</p><h2>Paper workspace</h2><p className="muted">Extract sections with provenance and compare supplied papers. Missing fields stay explicit.</p></div>
      <label className="button primary">Upload paper<input type="file" hidden disabled={busy} accept=".pdf,.docx,.txt,.md" onChange={upload} /></label>
    </div>
    {error && <ErrorState message={error} />}{status && <p role="status">{status}</p>}{busy && <LoadingState />}
    <div className="grid two-col"><article className="panel"><h3>Select papers</h3>
      {papers.length ? papers.map(paper => {
        const id = String(paper.document_id);
        return <label className="list-item" key={id}><input type="checkbox" checked={selected.includes(id)} disabled={busy} onChange={event => setSelected(current => event.target.checked ? [...current, id] : current.filter(value => value !== id))} /> {String(paper.title)}<p className="muted">{String(paper.source)} · {String(paper.status)}</p></label>;
      }) : <EmptyState>Upload a research paper or bootstrap permitted OpenAlex metadata.</EmptyState>}
      <button className="button primary" disabled={busy || !selected.length || selected.length > 20} onClick={() => void analyze()}>{selected.length > 1 ? 'Compare selected papers' : 'Extract selected paper'}</button>
    </article><article className="panel"><h3>Extracted fields and source locations</h3>{analysis ? <JsonPanel value={analysis} /> : <EmptyState>Select a paper for extraction, or two or more for comparison.</EmptyState>}</article></div>
  </section>;
}
