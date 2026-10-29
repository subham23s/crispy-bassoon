import type { ReactNode } from 'react';

export function LoadingState({ label = 'Loading API data…' }: { label?: string }) { return <div className="state loading-state"><span className="spinner" />{label}</div>; }
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const connectionFailed = /failed to fetch|networkerror|load failed/i.test(message);
  return <div className="state error-state" role="alert">
    <strong>Unable to load this API resource</strong>
    <p>{connectionFailed ? 'The browser could not reach the configured API for this request.' : message}</p>
    {connectionFailed && <small className="error-hint">Check that the backend is running, NEXT_PUBLIC_API_URL points to it, and its CORS origins include this frontend address.</small>}
    {onRetry && <button className="secondary" onClick={onRetry}>Retry</button>}
  </div>;
}
export function EmptyState({ children = 'The API returned no records for this view.' }: { children?: ReactNode }) { return <div className="state">{children}</div>; }
export function JsonPanel({ value }: { value: unknown }) { return <pre className="data-block">{JSON.stringify(value, null, 2)}</pre>; }
