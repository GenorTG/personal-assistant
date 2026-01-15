'use client';

import { Info } from 'lucide-react';

interface MessageContextProps {
  contextUsed: any[];
}

export function MessageContext({ contextUsed }: MessageContextProps) {
  if (!contextUsed || contextUsed.length === 0) return null;

  return (
    <div className="mb-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded text-xs text-blue-700 flex items-center gap-2 max-w-3xl">
      <Info size={14} />
      <span>
        Used {contextUsed.length} relevant context{contextUsed.length > 1 ? 's' : ''} from past
        conversations
      </span>
    </div>
  );
}




