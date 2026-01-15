'use client';

import { useState, useRef, useEffect, useCallback, ReactNode } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface SidebarProps {
  children: ReactNode;
  title?: string | ReactNode;
  onClose?: () => void;
  initialWidth?: number;
  minWidth?: number;
  maxWidth?: number;
  side?: 'left' | 'right';
  className?: string;
  onWidthChange?: (width: number) => void;
  headerActions?: ReactNode;
}

export default function Sidebar({
  children,
  title,
  onClose,
  initialWidth = 384,
  minWidth = 200,
  maxWidth = 800,
  side = 'right',
  className = '',
  onWidthChange,
  headerActions,
}: SidebarProps) {
  const [width, setWidth] = useState(initialWidth);
  const [isResizing, setIsResizing] = useState(false);
  const sidebarRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isResizing) return;

      const newWidth = side === 'right' ? window.innerWidth - e.clientX : e.clientX;

      if (newWidth >= minWidth && newWidth <= maxWidth) {
        setWidth(newWidth);
        onWidthChange?.(newWidth);
      }
    },
    [isResizing, minWidth, maxWidth, side, onWidthChange]
  );

  const handleMouseUp = useCallback(() => {
    setIsResizing(false);
  }, []);

  useEffect(() => {
    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';

      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };
    }
    return undefined;
  }, [isResizing, handleMouseMove, handleMouseUp]);

  const hasHeader = title || onClose || headerActions;

  return (
    <div
      ref={sidebarRef}
      className={cn(
        'flex flex-col h-full max-h-full overflow-hidden overflow-x-hidden bg-background',
        className
      )}
      style={{
        width: `${width}px`,
        position: 'relative',
        maxHeight: '100vh',
        maxWidth: '100vw',
      }}
    >
      <div
        onMouseDown={handleMouseDown}
        className={cn(
          'absolute top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary transition-colors z-10',
          side === 'right' ? '-left-0.5' : '-right-0.5',
          isResizing && 'bg-primary'
        )}
        style={{ cursor: 'col-resize' }}
      />

      <div className={cn("hidden", hasHeader && "block flex-shrink-0 p-4 border-b border-border flex justify-between items-center")}>
        <div className={cn("hidden", title && "block text-xl font-bold")}>
          {typeof title === 'string' ? <h2>{title}</h2> : title}
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <div className={cn("hidden", headerActions && "block")}>{headerActions}</div>
          <div className={cn("hidden", onClose && "block")}>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              className="h-8 w-8"
              title="Close"
            >
              <X size={20} />
            </Button>
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1 min-h-0 overflow-x-hidden">
        <div className="overflow-x-hidden max-w-full" style={{ width: '100%', maxWidth: '100%' }}>
          {children}
        </div>
      </ScrollArea>
    </div>
  );
}
