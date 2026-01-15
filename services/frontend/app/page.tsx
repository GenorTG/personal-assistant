'use client';

import { AppLayout } from '@/components/layout/AppLayout';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ServiceStatusProvider } from '@/contexts/ServiceStatusContext';

// This is a client component - Next.js will handle SSR correctly
// All child components handle their own client-only logic
export default function Home() {
  return (
    <ServiceStatusProvider>
      <ErrorBoundary>
        <AppLayout />
      </ErrorBoundary>
    </ServiceStatusProvider>
  );
}
