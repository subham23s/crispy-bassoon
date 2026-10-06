import type { ReactNode } from 'react';

export function LoadingState({ label = 'Loading API data…' }: { label?: string }) { return <div className="state loading-state"><span className="spinner" />{label}</div>; }
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) { return <div className="state error-state"><strong>Unable to load this API resource</strong><p>{message}</p>{onRetry && <button className="secondary" onClick={onRetry}>Retry</button>}</div>; }
export function EmptyState({ children = 'The API returned no records for this view.' }: { children?: ReactNode }) { return <div className="state">{children}</div>; }
export function JsonPanel({ value }: { value: unknown }) { return <pre className="data-block">{JSON.stringify(value, null, 2)}</pre>; }
