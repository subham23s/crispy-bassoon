'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { FormEvent, useEffect, useState } from 'react';
import { useAuth } from './auth-provider';

interface NavSection {
  title: string;
  items: { href: string; label: string; icon: string }[];
}

const navSections: NavSection[] = [
  {
    title: 'RESEARCH',
    items: [
      { href: '/ask', label: 'Research chat', icon: '◈' },
      { href: '/documents', label: 'Evidence library', icon: '↥' },
      { href: '/sources', label: 'Source coverage', icon: '◎' },
    ],
  },
  {
    title: 'WORKSPACE',
    items: [
      { href: '/settings', label: 'Settings', icon: '⚙' },
    ],
  },
];

const allNavItems = navSections.flatMap((s) => s.items);

function AuthScreen() {
  const { api, signIn } = useAuth();
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; error?: boolean }>({ text: '' });
  const [health, setHealth] = useState('Checking API…');

  useEffect(() => {
    api.health().then((value) => setHealth(value.status === 'ok' ? 'API is online' : 'API is online · optional services degraded')).catch(() => setHealth('API is unavailable'));
  }, [api]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (register && password !== confirm) { setStatus({ text: 'Passwords do not match.', error: true }); return; }
    if (busy) return;
    setBusy(true);
    setStatus({ text: register ? 'Creating workspace…' : 'Signing in…' });
    try { await signIn(email, password, register); }
    catch (error) { setStatus({ text: error instanceof Error ? error.message : 'Authentication failed.', error: true }); }
    finally { setBusy(false); }
  }

  async function handleDemoLogin() {
    if (busy) return;
    setBusy(true);
    setStatus({ text: 'Connecting to demo workspace…' });
    const demoEmail = 'demo@cybersecra.local';
    const demoPass = 'DemoPassword123!';
    try {
      try {
        await signIn(demoEmail, demoPass, false);
      } catch {
        await signIn(demoEmail, demoPass, true);
      }
    } catch (error) {
      setStatus({ text: error instanceof Error ? error.message : 'Demo access failed.', error: true });
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-layout"><section className="auth-card">
    <div className="brand"><span className="brand-mark">CX</span><span><strong>CyberSecRA-X</strong><small>Evidence-aware intelligence</small></span></div>
    <p className="eyebrow accent">PRIVATE EVIDENCE WORKSPACE</p>
    <h1>{register ? 'Create your research workspace' : 'Sign in to your research workspace'}</h1>
    <p className="muted">Use an account to keep documents and defensive analysis scoped to your session. Credentials are never sent anywhere except the configured API.</p>
    <div className="health-line"><span className={`status-dot ${health.includes('online') ? 'online' : ''}`} />{health}</div>
    <form onSubmit={submit} className="stack-form">
      {status.text && <p className={status.error ? 'form-error' : 'form-status'}>{status.text}</p>}
      <label htmlFor="email">Email address</label><input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" placeholder="you@organization.com" />
      <label htmlFor="password">Password (min 10 characters)</label><input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={10} autoComplete={register ? 'new-password' : 'current-password'} />
      {register && <><label htmlFor="confirm">Confirm password</label><input id="confirm" type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required minLength={10} autoComplete="new-password" /></>}
      <button className="button primary" type="submit" disabled={busy}>{busy ? 'Connecting…' : register ? 'Create account →' : 'Sign in →'}</button>
      <div style={{ textAlign: 'center', margin: '8px 0 2px', color: 'var(--muted)', fontSize: '0.8rem' }}>— or —</div>
      <button type="button" className="button secondary" onClick={handleDemoLogin} disabled={busy} style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
        <span>⚡</span> Instant Demo Access
      </button>
    </form>
    <p className="switch-copy">{register ? 'Already have an account?' : 'Need an account?'} <button className="link-button" onClick={() => { setRegister(!register); setStatus({ text: '' }); }} type="button">{register ? 'Sign in' : 'Register'}</button></p>
  </section></main>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, signOut, api } = useAuth();
  const pathname = usePathname();
  const [health, setHealth] = useState('Checking API…');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  useEffect(() => { if (user) api.health().then((v) => setHealth(v.status === 'ok' ? 'Health check OK' : 'Health check degraded')).catch(() => setHealth('API unavailable')); }, [api, user]);
  useEffect(() => { setMobileNavOpen(false); }, [pathname]);
  if (loading) return <div className="state-screen"><span className="spinner" />Restoring session…</div>;
  if (!user) return <AuthScreen />;
  return <div className="app-frame">
    {mobileNavOpen && <button className="mobile-nav-backdrop" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />}
    <aside className={`sidebar ${mobileNavOpen ? 'mobile-open' : ''}`}><Link href="/ask" className="brand"><span className="brand-mark">CX</span><span><strong>CyberSecRA-X</strong><small>Cybersecurity research assistant</small></span></Link>
      <div className="workspace"><span className="eyebrow">YOUR RESEARCH</span><strong>Evidence Lab</strong><small>Answers grounded in sources</small></div>
      <nav className="nav-list" aria-label="Primary navigation">
        {navSections.map((section) => (
          <div key={section.title} className="nav-section-group">
            <div className="nav-section-title">{section.title}</div>
            {section.items.map((item) => (
              <Link
                className={`nav-link ${pathname === item.href ? 'active' : ''}`}
                href={item.href}
                key={item.href}
              >
                <span aria-hidden="true">{item.icon}</span>
                {item.label}
              </Link>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-footer"><span className={`status-dot ${health === 'Health check OK' ? 'online' : ''}`} />{health}<button className="link-button" onClick={() => void signOut()}>Sign out</button></div>
    </aside>
    <main className="main-content"><header className="topbar"><div className="topbar-title"><button className="mobile-menu-button" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation" aria-expanded={mobileNavOpen}>☰</button><div><p className="eyebrow">CYBERSECURITY RESEARCH PLATFORM</p><h1>{allNavItems.find((item) => item.href === pathname)?.label ?? 'Research workspace'}</h1></div></div><div className="identity"><span className="health-pill"><span className={`status-dot ${health === 'Health check OK' ? 'online' : ''}`} />{health}</span><span>{user.email}</span><button className="avatar" onClick={() => void signOut()} aria-label="Sign out">↪</button></div></header>{children}</main>
  </div>;
}
