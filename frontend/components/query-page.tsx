'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { useAuth } from './auth-provider';
import { EmptyState, ErrorState, JsonPanel, LoadingState } from './data-state';
import type { JsonRecord, QueryResult } from '@/types/api';

interface QueryPageProps { title: string; eyebrow: string; description: string; placeholder: string; initialQuery?: string; mode?: string; endpoint?: 'query' | 'vulnerability'; }

export function QueryPage({ title, eyebrow, description, placeholder, initialQuery = '', mode = 'RESEARCHER', endpoint = 'query' }: QueryPageProps) {
  const { api } = useAuth();
  const [input, setInput] = useState(initialQuery);
  const [answerStyle, setAnswerStyle] = useState('balanced');
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
        }, false, undefined, controller.current.signal, answerStyle);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The API request failed.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { if (initialQuery) void run(initialQuery); }, [initialQuery]); // eslint-disable-line react-hooks/exhaustive-deps
  function submit(event: FormEvent) { event.preventDefault(); void run(); }
  const evidence: JsonRecord[] = Array.isArray(result?.evidence) ? result.evidence : [];
  const claims: JsonRecord[] = Array.isArray(result?.claims) ? result.claims as JsonRecord[] : [];
  const conflicts: JsonRecord[] = Array.isArray(result?.conflicts) ? result.conflicts as JsonRecord[] : [];
  const scoreComponents = result?.cers?.components ? Object.entries(result.cers.components) : [];
  const suggestions = endpoint === 'vulnerability'
    ? [
        { label: 'MOVEit Transfer', query: 'CVE-2023-34362' },
        { label: 'Log4Shell', query: 'CVE-2021-44228' },
        { label: 'Citrix Bleed', query: 'CVE-2023-4966' },
      ]
    : [
        { label: 'Nmap', query: 'What can Nmap reveal about hosts and services on an authorized lab network?' },
        { label: 'Wireshark', query: 'How do I use Wireshark display filters to inspect DNS traffic?' },
        { label: 'Snort', query: 'How do Snort 3 rules detect suspicious network traffic?' },
        { label: 'Incident response', query: 'What are the core phases of cybersecurity incident response?' },
        { label: 'NIST CSF 2.0', query: 'What are the six functions in NIST Cybersecurity Framework 2.0?' },
        { label: 'Compare tools', query: 'Compare Nmap and Wireshark: what question does each tool help answer?' },
      ];

  return <section className="page">
    <div className="section-heading"><div><p className="eyebrow accent">{eyebrow}</p><h2>{title}</h2><p className="muted">{description}</p></div></div>
    <div className="chat-promises" aria-label="How this assistant differs">
      <span><b>01</b> Answers linked to sources</span>
      <span><b>02</b> Claims checked against evidence</span>
      <span><b>03</b> Says when evidence is not enough</span>
    </div>
    <form className="panel chat-composer" onSubmit={submit}>
      <div className="form-row">
        <label><span className="label">{endpoint === 'vulnerability' ? 'CVE identifier' : 'Your question'}</span><input className="control" value={input} onChange={(event) => setInput(event.target.value)} placeholder={placeholder} /></label>
        <button className="button primary" disabled={loading}>{loading ? `${stage || 'Analyzing'}…` : 'Research answer →'}</button>
      </div>
      {endpoint !== 'vulnerability' && <div className="form-row" style={{ gridTemplateColumns: 'minmax(180px, 260px) 1fr', marginTop: '12px' }}>
        <label><span className="label">Answer style</span><select className="control" value={answerStyle} onChange={event => setAnswerStyle(event.target.value)} disabled={loading}><option value="balanced">Balanced explanation</option><option value="quick">Quick answer</option><option value="steps">Step by step</option><option value="compare">Compare evidence</option></select></label>
        <small className="muted" style={{ alignSelf: 'end', paddingBottom: '12px' }}>Citations and evidence checks stay enabled for every style.</small>
      </div>}
      <div className="chip-row">
        <span className="chip-label">Quick suggestions:</span>
        {suggestions.map((s) => (
          <button key={s.label} type="button" className="chip" onClick={() => { setInput(s.query); void run(s.query); }}>
            {s.label}
          </button>
        ))}
      </div>
    </form>
    <details className="panel"><summary>Saved answer history ({history.length})</summary>{historyError && <ErrorState message={historyError} />}{!history.length && !historyError && <p className="muted">No saved answers yet.</p>}<div className="card-list">{history.map(saved => <button className="list-item" key={saved.answer_id} disabled={loading} onClick={() => { setResult(saved); setInput(saved.query ?? ''); setError(''); }}><strong>{saved.query}</strong><p className="muted">{String(saved.created_at ?? '')} · {saved.abstained ? 'Abstained' : 'Evidence response'}</p></button>)}</div></details>
    {loading && <div className="panel"><p className="eyebrow">LIVE PIPELINE</p><p className="muted">{stage || 'Starting'} · generation is provisional until verification completes.</p>{streamText && <p className="answer">{streamText}</p>}<button className="button secondary" onClick={() => controller.current?.abort()}>Cancel</button><LoadingState label="Waiting for verified completion…" /></div>}
    {result?.answer_id && <div className="panel"><h3>Export this verified answer</h3>{['markdown', 'json', 'pdf', 'docx'].map(format => <button key={format} className="button secondary" disabled={exporting} onClick={() => void download(format)} style={{ marginRight: '8px' }}>{format.toUpperCase()}</button>)}</div>}
    {error && <ErrorState message={error} onRetry={() => void run()} />}
    {!loading && !error && !result && <EmptyState>Ask a cybersecurity question to get a source-linked answer, evidence excerpts, and claim checks.</EmptyState>}
    {!loading && !error && result && <>
      <div className="grid two-col">
        <article className="panel">
          <div className="research-answer-head"><p className="eyebrow">RESEARCH ANSWER</p><span className={`badge ${result.abstained ? 'warn' : 'good'}`}>{result.abstained ? 'Evidence insufficient' : 'Evidence reviewed'}</span></div>
          <h3>{result.query ?? 'Your question'}</h3>
          <p className="answer">{String(result.answer ?? streamText ?? 'The API returned no narrative answer.').split(/(\[C\d+\])/g).map((part, index) => {
            const citation = part.match(/^\[C(\d+)\]$/);
            if (!citation) return part;
            const evidenceIndex = Number(citation[1]) - 1;
            if (evidenceIndex < 0 || evidenceIndex >= evidence.length) return part;
            return <a key={`${part}-${index}`} className="inline-citation" href={`#evidence-${evidenceIndex}`} onClick={(event) => { event.preventDefault(); document.getElementById(`evidence-${evidenceIndex}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }}>{part}</a>;
          })}</p>
          <div className="metric-row">
            {result.cers && <div className="metric score-metric"><span className="muted">Evidence signal (CERS)</span><strong>{result.cers.percentage ?? '—'}%</strong><small>Project score, not a probability</small></div>}
            <div className="metric"><span className="muted">Sources retrieved</span><strong>{evidence.length}</strong></div>
            <div className="metric"><span className="muted">Claims checked</span><strong>{claims.length}</strong></div>
          </div>
          {result.cers?.methodology && <details className="score-details"><summary>How the evidence score is calculated</summary><p className="muted">{result.cers.methodology}</p>{scoreComponents.length > 0 && <div className="score-breakdown">{scoreComponents.map(([name, value]) => <div className="score-component" key={name}><div><span>{name.replaceAll('_', ' ')}</span><strong>{Math.round(Number(value) * 100)}%</strong></div><div className="score-track"><i style={{ width: `${Math.max(0, Math.min(100, Number(value) * 100))}%` }} /></div></div>)}</div>}<small className="muted">Calibration: {String(result.cers.calibration_status ?? 'not reported')}.</small></details>}
        </article>
        <article className="panel">
          <h3>Evidence trail ({evidence.length})</h3>
          <p className="muted">Open a source to verify where the answer came from.</p>
          {evidence.length ? <div className="card-list">{evidence.map((item, index) => {
            const provenance = item.provenance && typeof item.provenance === 'object' ? item.provenance as JsonRecord : {};
            const publicationDate = provenance.publication_date ?? provenance.update_date;
            return <div className="list-item" id={`evidence-${index}`} key={String(item.chunk_id ?? item.id ?? index)}><header><strong>[C{index + 1}] {String(item.source ?? item.title ?? 'Source not reported')}</strong><span className="badge">source</span></header><p>{String(item.text ?? item.content ?? 'No excerpt reported.')}</p><small className="muted">{[item.title, item.section, item.page_number ? `Page ${item.page_number}` : '', item.version ? `Version ${item.version}` : '', publicationDate ? `Published/updated ${String(publicationDate).slice(0, 10)}` : ''].filter(Boolean).map(String).join(' · ')}</small>{typeof item.url === 'string' && item.url && <a className="source-link" href={item.url} target="_blank" rel="noreferrer">Open original source ↗</a>}</div>;
          })}</div> : <EmptyState>No evidence chunks were reported by the API.</EmptyState>}
        </article>
      </div>
      <div className="panel">
        <h3>What the evidence supports</h3>
        {claims.length ? <div className="card-list">{claims.map((claim, index) => {
          const citationIds = Array.isArray(claim.citation_ids) ? claim.citation_ids.map(String) : [];
          const citations = citationIds.map(id => evidence.findIndex(item => String(item.chunk_id ?? item.id ?? '') === id)).filter(index => index >= 0);
          const status = String(claim.status ?? 'UNSPECIFIED');
          return <div className="list-item" key={String(claim.claim_id ?? index)}><header><span className={`badge ${status === 'SUPPORTED' ? 'good' : 'warn'}`}>{status.replaceAll('_', ' ')}</span>{typeof claim.support_score === 'number' && <span className="muted">Support {Math.round(claim.support_score * 100)}%</span>}</header><p>{String(claim.claim ?? 'Claim text not reported.')}</p>{Boolean(claim.explanation) && <small className="muted">{String(claim.explanation)}</small>}{citations.length > 0 && <div className="citation-links">Sources: {citations.map((sourceIndex, citationIndex) => <a key={`${sourceIndex}-${citationIndex}`} href={`#evidence-${sourceIndex}`} onClick={(event) => { event.preventDefault(); document.getElementById(`evidence-${sourceIndex}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }}>[C{sourceIndex + 1}]</a>)}</div>}</div>;
        })}</div> : <EmptyState>No claims were reported.</EmptyState>}
        {conflicts.length > 0 && <div className="conflicts-block"><p className="eyebrow">POSSIBLE SOURCE DISAGREEMENTS</p><p className="muted">The system keeps these differences visible instead of merging them into one claim.</p>{conflicts.map((conflict, index) => <div className="list-item" key={index}><strong>{String(conflict.source_a ?? 'Source A')} ↔ {String(conflict.source_b ?? 'Source B')}</strong><p>{String(conflict.conflict ?? conflict.claim_a ?? 'Conflicting passages were identified for review.')}</p></div>)}</div>}
        {Array.isArray(result.limitations) && result.limitations.length > 0 && <div style={{ marginTop: '16px' }}><p className="eyebrow">LIMITATIONS</p><ul>{result.limitations.map((item, index) => <li key={index} className="muted">{String(item)}</li>)}</ul></div>}
      </div>
      <details className="panel raw-contract-panel">
        <summary className="eyebrow">▶ Inspect Raw JSON Contract</summary>
        <JsonPanel value={result} />
      </details>
    </>}
  </section>;
}
