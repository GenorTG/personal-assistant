'use client';

import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface FloatingPanelProps {
  children: React.ReactNode;
  title?: string;
  onClose: () => void;
  className?: string;
  maxWidth?: string;
  maxHeight?: string;
}

export default function FloatingPanel({
  children,
  title,
  onClose,
  className = '',
  maxWidth = '90vw',
  maxHeight = '90vh',
}: FloatingPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  // Prevent body scroll when panel is open
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={panelRef}
        className={cn(
          'bg-background border-2 border-border rounded shadow-2xl',
          'flex flex-col',
          'overflow-hidden overflow-x-hidden',
          className
        )}
        style={{
          width: `calc(100vw - 2rem)`,
          height: `calc(100vh - 2rem)`,
          maxWidth: `min(${maxWidth}, calc(100vw - 2rem))`,
          maxHeight: `min(${maxHeight}, calc(100vh - 2rem))`,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {(title || typeof onClose === 'function') && (
          <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
            {title && <h2 className="text-lg font-semibold">{title}</h2>}
            {typeof onClose === 'function' && (
              <Button
                variant="ghost"
                size="icon"
                onClick={onClose}
                className="h-8 w-8"
              >
                <X size={16} />
              </Button>
            )}
          </div>
        )}
        <div className="flex-1 overflow-hidden min-h-0">{children}</div>
      </div>
    </div>
  );
}

