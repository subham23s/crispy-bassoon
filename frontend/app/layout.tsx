import type { Metadata } from 'next';
import { AuthProvider } from '@/components/auth-provider';
import { AppShell } from '@/components/app-shell';
import './globals.css';

export const metadata: Metadata = { title: 'CyberSecRA-X', description: 'Evidence-aware cybersecurity research intelligence' };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AuthProvider><AppShell>{children}</AppShell></AuthProvider></body></html>;
}
