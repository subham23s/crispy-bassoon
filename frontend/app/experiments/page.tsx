'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useAuth } from '@/components/auth-provider';
import { EmptyState, ErrorState, LoadingState } from '@/components/data-state';
import type { ExperimentInput, ExperimentRecord } from '@/types/api';

const empty: ExperimentInput = { name: '', dataset: '', model: '', hyperparameters: {}, notes: '', status: 'created' };
const statuses: ExperimentInput['status'][] = ['created', 'running', 'completed', 'failed', 'cancelled'];

export default function ExperimentsPage() {
  const { api } = useAuth();
  const [rows, setRows] = useState<ExperimentRecord[]>([]);
  const [form, setForm] = useState<ExperimentInput>(empty);
  const [parameters, setParameters] = useState('{}');
  const [editing, setEditing] = useState('');
  const [selected, setSelected] = useState('');
  const [metric, setMetric] = useState('');
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true); setError('');
    try { setRows((await api.compareExperiments()).experiments); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Experiment request failed.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [api]);
  function reset() { setEditing(''); setForm(empty); setParameters('{}'); }
  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError('');
    try {
      const parsed: unknown = JSON.parse(parameters);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Hyperparameters must be a JSON object.');
      const input = { ...form, hyperparameters: parsed as Record<string, unknown> };
      if (editing) await api.updateExperiment(editing, input);
      else await api.createExperiment(input);
      reset(); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Save failed.'); }
    finally { setSaving(false); }
  }
  async function record(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError('');
    try {
      if (!value.trim() || !Number.isFinite(Number(value))) throw new Error('Enter a finite measured number.');
      await api.recordMetric(selected, metric.trim(), Number(value));
      setMetric(''); setValue(''); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Metric save failed.'); }
    finally { setSaving(false); }
  }
  async function remove(id: string) {
    setSaving(true); setError('');
    try { await api.deleteExperiment(id); if (editing === id) reset(); if (selected === id) setSelected(''); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Delete failed.'); }
    finally { setSaving(false); }
  }
  const metricNames = [...new Set(rows.flatMap(row => (row.metrics ?? []).map(item => item.metric_name)))].sort();

  return <section className="page">
    <div className="section-heading"><div><p className="eyebrow accent">RESEARCH OPERATIONS</p><h2>Experiment tracker</h2><p className="muted">Record datasets, models, parameters, and your measured results. Metrics are user-supplied observations.</p></div><button className="button secondary" onClick={() => void load()} disabled={loading || saving}>Refresh</button></div>
    {error && <ErrorState message={error} />}
    <div className="grid two-col">
      <form className="panel" onSubmit={save}><h3>{editing ? 'Edit experiment' : 'Create experiment'}</h3>
        {(['name', 'dataset', 'model', 'notes'] as const).map(key => <label key={key}><span className="label">{key}</span><input className="control" required={key === 'name'} value={form[key]} onChange={event => setForm({ ...form, [key]: event.target.value })} /></label>)}
        <label><span className="label">Status</span><select className="control" value={form.status} onChange={event => setForm({ ...form, status: event.target.value as ExperimentInput['status'] })}>{statuses.map(status => <option key={status}>{status}</option>)}</select></label>
        <label><span className="label">Hyperparameters (JSON object)</span><textarea className="control" rows={4} value={parameters} onChange={event => setParameters(event.target.value)} /></label>
        <button className="button primary" disabled={saving}>{saving ? 'Saving…' : 'Save experiment'}</button>{editing && <button type="button" className="button secondary" onClick={reset}>Cancel editing</button>}
      </form>
      <form className="panel" onSubmit={record}><h3>Record a measured metric</h3><p className="muted">Recording the same metric name updates its value. Include units in the name and measurement provenance in the experiment notes.</p>
        <label><span className="label">Experiment</span><select className="control" required value={selected} onChange={event => setSelected(event.target.value)}><option value="">Select experiment</option>{rows.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></label>
        <label><span className="label">Metric name</span><input className="control" required maxLength={120} value={metric} onChange={event => setMetric(event.target.value)} /></label>
        <label><span className="label">Measured value</span><input className="control" required type="number" step="any" value={value} onChange={event => setValue(event.target.value)} /></label>
        <button className="button primary" disabled={saving || !selected}>Save metric</button>
      </form>
    </div>
    {loading && <LoadingState />}
    {!loading && !rows.length && <EmptyState>No persisted experiments have been created.</EmptyState>}
    {!!rows.length && <div className="panel"><h3>Experiments and measured comparison</h3><div style={{ overflowX: 'auto' }}><table><thead><tr><th>Name</th><th>Dataset / model</th><th>Status</th>{metricNames.map(name => <th key={name}>{name}</th>)}<th>Actions</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.name}<p className="muted">{row.notes}</p></td><td>{row.dataset || '—'} / {row.model || '—'}</td><td>{row.status}</td>{metricNames.map(name => <td key={name}>{row.metrics?.find(item => item.metric_name === name)?.metric_value ?? 'Not recorded'}</td>)}<td><button className="button secondary" disabled={saving} onClick={() => { setEditing(row.id); setForm(row); setParameters(JSON.stringify(row.hyperparameters, null, 2)); }}>Edit</button><button className="button secondary" disabled={saving} onClick={() => void remove(row.id)}>Delete</button></td></tr>)}</tbody></table></div></div>}
  </section>;
}
