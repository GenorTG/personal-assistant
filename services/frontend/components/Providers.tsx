'use client';

import { ReactNode } from 'react';
import { SamplerSettingsProvider } from '@/contexts/SamplerSettingsContext';
import { SettingsProvider } from '@/contexts/SettingsContext';
import { ToastProvider } from '@/contexts/ToastContext';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <SettingsProvider>
        <SamplerSettingsProvider>
          {children}
        </SamplerSettingsProvider>
      </SettingsProvider>
    </ToastProvider>
  );
}

