'use client';

import { FormEvent, useState } from 'react';
import { useAuth } from '@/components/auth-provider';
import { EmptyState, ErrorState, JsonPanel, LoadingState } from '@/components/data-state';
import { GraphView } from '@/components/graph-view';
import type { JsonRecord } from '@/types/api';

const sampleEntities = [
  { label: 'T1059 (Command Execution)', id: 'T1059' },
  { label: 'T1078 (Valid Accounts)', id: 'T1078' },
  { label: 'CVE-2023-34362 (MOVEit)', id: 'CVE-2023-34362' },
  { label: 'APT29 (Cozy Bear)', id: 'APT29' },
];

export default function GraphPage() {
  const { api } = useAuth();
  const [entity, setEntity] = useState('T1059');
  const [result, setResult] = useState<JsonRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function loadGraph(target = entity) {
    if (!target.trim()) return;
    setLoading(true);
    setError('');
    try {
      setResult(await api.graph(target.trim()));
    } catch (x) {
      setError(x instanceof Error ? x.message : 'Graph request failed.');
    } finally {
      setLoading(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void loadGraph();
  }

  const nodes = Array.isArray(result?.nodes) ? result.nodes : [];

  return (
    <section className="page">
      <div className="section-heading">
        <div>
          <p className="eyebrow accent">PROVENANCE GRAPH</p>
          <h2>Entity graph</h2>
          <p className="muted">Relationships are derived from the local evidence corpus and are not invented when unavailable.</p>
        </div>
      </div>

      <form className="panel" onSubmit={submit}>
        <div className="form-row">
          <label>
            <span className="label">Entity identifier</span>
            <input
              value={entity}
              onChange={(e) => setEntity(e.target.value)}
              placeholder="e.g. T1059, T1078, CVE-2023-34362"
            />
          </label>
          <button className="button primary" disabled={loading}>
            {loading ? 'Searching…' : 'Inspect graph →'}
          </button>
        </div>

        <div className="chip-row">
          <span className="chip-label">Suggestions:</span>
          {sampleEntities.map((item) => (
            <button
              key={item.id}
              type="button"
              className="chip"
              onClick={() => {
                setEntity(item.id);
                void loadGraph(item.id);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      </form>

      {loading && <LoadingState label="Traversing entity graph relationships…" />}
      {error && <ErrorState message={error} />}

      {!loading && !error && !result && (
        <EmptyState>Enter an entity identifier above or click a suggestion to inspect relationships.</EmptyState>
      )}

      {!loading && !error && result && (
        <>
          <div className="panel">
            <div className="panel-head">
              <div>
                <p className="eyebrow">GRAPH VISUALIZATION</p>
                <h3>Resolved Entities ({nodes.length} nodes)</h3>
              </div>
            </div>

            {nodes.length > 0 ? (
              <GraphView
                value={result}
                onSelect={(value) => {
                  setEntity(value);
                  void loadGraph(value);
                }}
              />
            ) : (
              <EmptyState>
                No graph edges or nodes recorded for <strong>{entity}</strong> in the current local corpus.
              </EmptyState>
            )}
          </div>

          <details className="panel raw-contract-panel">
            <summary className="eyebrow">▶ Inspect Raw Graph JSON</summary>
            <JsonPanel value={result} />
          </details>
        </>
      )}
    </section>
  );
}
