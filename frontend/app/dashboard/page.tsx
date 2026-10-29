'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useAuth } from '@/components/auth-provider';
import { EmptyState, ErrorState, LoadingState } from '@/components/data-state';
import type { DocumentsResponse, Health } from '@/types/api';

export default function DashboardPage() {
  const { api } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [detail, setDetail] = useState<Health | null>(null);
  const [docs, setDocs] = useState<DocumentsResponse | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.healthDetailed(), api.documents()])
      .then(([h, d]) => {
        setDetail(h);
        setHealth(h);
        setDocs(d);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Unable to load dashboard data.'));
  }, [api]);

  if (error) {
    return (
      <section className="page">
        <ErrorState message={error} />
      </section>
    );
  }

  if (!detail || !docs) {
    return (
      <section className="page">
        <LoadingState label="Loading workspace pulse…" />
      </section>
    );
  }

  const capabilities = detail.capabilities ? Object.entries(detail.capabilities) : [];

  return (
    <section className="page">
      {/* Hero Welcome */}
      <div className="hero">
        <div>
          <p className="eyebrow accent">EVIDENCE-AWARE INTELLIGENCE</p>
          <h2>
            Ask better questions.<br />
            <em>Trust what you can verify.</em>
          </h2>
          <p>
            Trace answers to attributed sources, inspect claim-level support, and abstain when evidence is insufficient.
          </p>
          <div style={{ marginTop: '8px' }}>
            <Link href="/ask" className="button primary">
              Start a research query →
            </Link>
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid stats">
        <div className="stat">
          <span>Workspace Documents</span>
          <strong>{docs.documents?.length ?? 0}</strong>
          <small>current session</small>
        </div>
        <div className="stat">
          <span>API Runtime</span>
          <strong>{health?.runtime ?? 'fastapi'}</strong>
          <small>reported by backend</small>
        </div>
        <div className="stat">
          <span>Evidence Mode</span>
          <strong>{health?.evidence_mode ?? 'curated-local'}</strong>
          <small>no assumptions made</small>
        </div>
        <div className="stat">
          <span>Active Capabilities</span>
          <strong>{capabilities.filter(([, v]) => v === true).length}</strong>
          <small>enabled by API</small>
        </div>
      </div>

      {/* Main Two-Col Grid */}
      <div className="grid two-col">
        {/* Quick Launchpad */}
        <div className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">INVESTIGATION LAUNCHPAD</p>
              <h3>What would you like to investigate?</h3>
            </div>
          </div>
          <div className="card-list" style={{ marginTop: '14px' }}>
            <Link href="/ask" className="list-item" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
              <header>
                <strong>◈ Ask Research Question</strong>
                <span className="badge">Natural language</span>
              </header>
              <p className="muted" style={{ marginTop: '4px', fontSize: '0.82rem' }}>
                Query technical topics with claim-level verification and provenance citations.
              </p>
            </Link>

            <Link href="/vulnerabilities" className="list-item" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
              <header>
                <strong>! CVE Vulnerability Intelligence</strong>
                <span className="badge">SOC analyst</span>
              </header>
              <p className="muted" style={{ marginTop: '4px', fontSize: '0.82rem' }}>
                Look up a specific CVE identifier with official advisories and mitigations.
              </p>
            </Link>

            <Link href="/graph" className="list-item" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
              <header>
                <strong>⌘ Entity Provenance Graph</strong>
                <span className="badge">Graph analysis</span>
              </header>
              <p className="muted" style={{ marginTop: '4px', fontSize: '0.82rem' }}>
                Inspect interactive relationships between tactics, threat actors, and CVEs.
              </p>
            </Link>

            <Link href="/documents" className="list-item" style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}>
              <header>
                <strong>↥ Upload Evidence Document</strong>
                <span className="badge">Ingestion</span>
              </header>
              <p className="muted" style={{ marginTop: '4px', fontSize: '0.82rem' }}>
                Upload security reports, whitepapers, or advisory PDFs for local indexing.
              </p>
            </Link>
          </div>
        </div>

        {/* System Capabilities */}
        <div className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">SYSTEM CAPABILITIES</p>
              <h3>Engine Status & Modules</h3>
            </div>
            <span className="badge good">{health?.status ?? 'online'}</span>
          </div>

          {capabilities.length ? (
            <div className="card-list">
              {capabilities.slice(0, 8).map(([key, value]) => (
                <div className="list-item" key={key}>
                  <header>
                    <span>{key.replaceAll('_', ' ')}</span>
                    <strong style={{ color: value ? 'var(--green)' : 'var(--muted)' }}>
                      {value ? '✓ active' : 'disabled'}
                    </strong>
                  </header>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState>No capabilities reported.</EmptyState>
          )}
        </div>
      </div>
    </section>
  );
}
