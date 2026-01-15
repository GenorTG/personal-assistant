'use client';

import { cn } from '@/lib/utils';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface BackendStatusBarProps {
  isReady: boolean;
}

export function BackendStatusBar({ isReady }: BackendStatusBarProps) {
  return (
    <div className={cn("hidden w-full border-b px-4 py-2", !isReady && "block")}>
      <Alert variant="default" className="bg-yellow-50 border-yellow-200">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 bg-yellow-500 rounded animate-pulse"></span>
          <AlertDescription className="text-yellow-800">
            Waiting for backend to be ready...
          </AlertDescription>
        </div>
      </Alert>
    </div>
  );
}




