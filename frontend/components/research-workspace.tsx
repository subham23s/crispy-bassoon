'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useAuth } from './auth-provider';
import { EmptyState, ErrorState, JsonPanel, LoadingState } from './data-state';
import type { JsonRecord, QueryResult } from '@/types/api';

export function ResearchWorkspace() {
  const { api } = useAuth();
  const [workspaces, setWorkspaces] = useState<JsonRecord[]>([]);
  const [selected, setSelected] = useState('');
  const [items, setItems] = useState<unknown[]>([]);
  const [notes, setNotes] = useState<unknown[]>([]);
  const [evidence, setEvidence] = useState<unknown[]>([]);
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<QueryResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    api.workspaces().then(value => {
      if (!active) return;
      const rows = Array.isArray(value.workspaces) ? value.workspaces as JsonRecord[] : [];
      setWorkspaces(rows);
      setSelected(current => current || String(rows[0]?.id ?? ''));
    }).catch(reason => { if (active) setError(String(reason)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, revision]);

  useEffect(() => {
    let active = true;
    setItems([]); setNotes([]); setEvidence([]);
    if (selected) Promise.all([api.workspaceItems(selected), api.workspaceNotes(selected), api.workspaceEvidence(selected)]).then(([itemResult, noteResult, evidenceResult]) => {
      if (!active) return;
      setItems(Array.isArray(itemResult.items) ? itemResult.items : []);
      setNotes(Array.isArray(noteResult.notes) ? noteResult.notes : []);
      setEvidence(Array.isArray(evidenceResult.evidence) ? evidenceResult.evidence : []);
    }).catch(reason => { if (active) setError(String(reason)); });
    return () => { active = false; };
  }, [api, selected, revision]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError('');
    try { await work(); setRevision(value => value + 1); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Workspace request failed.'); }
    finally { setBusy(false); }
  }
  function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    void action(async () => { const result = await api.createWorkspace(name.trim()); setSelected(String((result.workspace as JsonRecord).id)); setAnswer(null); setName(''); });
  }
  function saveNote(event: FormEvent) { event.preventDefault(); if (selected && note.trim()) void action(async () => { await api.createNote(selected, note.trim()); setNote(''); }); }
  function ask(event: FormEvent) { event.preventDefault(); if (selected && question.trim()) void action(async () => { setAnswer(await api.query(question.trim(), 'RESEARCHER', selected)); setQuestion(''); }); }

  return <section className="page"><div className="section-heading"><div><p className="eyebrow accent">RESEARCH WORKSPACE</p><h2>Questions, notes, and evidence</h2><p className="muted">Persist research answers and source snapshots in your selected workspace.</p></div></div>
    {loading && <LoadingState />}{error && <ErrorState message={error} />}{busy && <LoadingState label="Saving workspace changes…" />}
    <div className="grid two-col"><div className="panel"><h3>Create or select workspace</h3><form className="form-row" onSubmit={create}><input className="control" aria-label="Workspace name" value={name} onChange={event => setName(event.target.value)} placeholder="Workspace name" required /><button className="button primary" disabled={busy}>Create</button></form>{workspaces.length ? <div className="card-list">{workspaces.map(workspace => <button disabled={busy} className={`list-item ${String(workspace.id) === selected ? 'active' : ''}`} key={String(workspace.id)} onClick={() => { setSelected(String(workspace.id)); setAnswer(null); }}>{String(workspace.name)}</button>)}</div> : <EmptyState>No workspaces yet.</EmptyState>}<h3>Saved evidence snapshots</h3><JsonPanel value={evidence} /></div>
      <div className="panel"><h3>Workspace records</h3>{selected ? <><form onSubmit={ask}><h4>Ask and save answer</h4><textarea className="control" aria-label="Research question" value={question} onChange={event => setQuestion(event.target.value)} required /><button className="button primary" disabled={busy}>Ask and save answer</button></form>
        {answer && <><h4>{answer.abstained ? 'Abstained: insufficient evidence' : 'Evidence response'}</h4><p className="answer">{answer.answer}</p>{answer.evidence?.map(chunk => <div className="list-item" key={String(chunk.chunk_id)}><strong>{String(chunk.source)}</strong><p>{String(chunk.text)}</p><button className="button secondary" disabled={busy} onClick={() => void action(async () => { await api.saveEvidence(selected, String(chunk.chunk_id)); })}>Save evidence to workspace</button></div>)}</>}
        <form onSubmit={saveNote}><h4>New note</h4><textarea className="control" aria-label="Research note" value={note} onChange={event => setNote(event.target.value)} required /><button className="button secondary" disabled={busy}>Save note</button></form><h4>Items and answers</h4><JsonPanel value={items} /><h4>Notes</h4><JsonPanel value={notes} /></> : <EmptyState>Select a workspace.</EmptyState>}</div>
    </div>
  </section>;
}
