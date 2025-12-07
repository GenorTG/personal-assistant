'use client';

import { useState, useRef, useEffect, useCallback, ReactNode } from 'react';

interface ResizableSidebarProps {
  children: ReactNode;
  initialWidth?: number;
  minWidth?: number;
  maxWidth?: number;
  side?: 'left' | 'right';
  className?: string;
  style?: React.CSSProperties;
  onWidthChange?: (width: number) => void;
}

export default function ResizableSidebar({
  children,
  initialWidth = 384, // 96 * 4 = 384px (w-96)
  minWidth = 200,
  maxWidth = 800,
  side = 'right',
  className = '',
  style = {},
  onWidthChange,
}: ResizableSidebarProps) {
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

      const newWidth =
        side === 'right'
          ? window.innerWidth - e.clientX
          : e.clientX;

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
  }, [isResizing, handleMouseMove, handleMouseUp]);

  return (
    <div
      ref={sidebarRef}
      className={className}
      style={{
        width: `${width}px`,
        position: 'relative',
        ...style,
      }}
    >
      {/* Resize handle */}
      <div
        onMouseDown={handleMouseDown}
        className={`absolute top-0 bottom-0 w-1 cursor-col-resize hover:bg-blue-500 transition-colors z-10 ${
          side === 'right' ? '-left-0.5' : '-right-0.5'
        } ${isResizing ? 'bg-blue-500' : 'bg-transparent'}`}
        style={{
          cursor: 'col-resize',
        }}
      />
      {children}
    </div>
  );
}

