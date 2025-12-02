'use client';

import { ReactNode } from 'react';
import { SamplerSettingsProvider } from '@/contexts/SamplerSettingsContext';
import { SettingsProvider } from '@/contexts/SettingsContext';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <SettingsProvider>
      <SamplerSettingsProvider>
        {children}
      </SamplerSettingsProvider>
    </SettingsProvider>
  );
}

