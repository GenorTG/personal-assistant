'use client';

import { useState, useEffect, useRef } from 'react';
import { Activity, Server, Brain, Mic, Volume2, Loader2, CheckCircle2, XCircle, AlertCircle, GripVertical, Terminal, X, Copy, Check, Trash2 } from 'lucide-react';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import { useServiceStatus } from '@/contexts/ServiceStatusContext';
import { useGenerationState } from '@/hooks/useGenerationState';
import { useDeveloperMode, BackendLogEntry } from '@/contexts/DeveloperModeContext';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';

export function DebugStatusPanel() {
  // Use WebSocket for real-time updates instead of polling
  const { isReady: backendReady, isChecking } = useBackendHealth({ interval: 10000, enabled: true }); // Reduced polling frequency
  const { statuses } = useServiceStatus();
  const isGenerating = useGenerationState();
  const { logs: apiLogs, clearLogs } = useDeveloperMode();
  const [modelLoaded, setModelLoaded] = useState<boolean>(false);
  const [modelName, setModelName] = useState<string>('');
  const [isModelLoading, setIsModelLoading] = useState<boolean>(false);
  
  const [isCollapsed, setIsCollapsed] = useState(false); // Start expanded so user can see it
  const [showLogs, setShowLogs] = useState(false); // Show/hide live logs
  const [copiedLogId, setCopiedLogId] = useState<string | null>(null);
  
  // Dragging state - use refs for immediate updates
  const panelRef = useRef<HTMLDivElement>(null);
  const isDraggingRef = useRef(false);
  const startXRef = useRef(0);
  const startYRef = useRef(0);
  const offsetXRef = useRef(0);
  const offsetYRef = useRef(0);
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);

  // Initialize position to bottom-right on mount (client-side only)
  useEffect(() => {
    if (position === null && typeof window !== 'undefined') {
      const panelWidth = isCollapsed ? 48 : 320;
      const panelHeight = isCollapsed ? 48 : (showLogs ? 500 : 200);
      const x = window.innerWidth - panelWidth - 16;
      const y = window.innerHeight - panelHeight - 16;
      setPosition({ x, y });
    }
  }, [position, isCollapsed, showLogs]);

  // Apply position to DOM when position changes or panel ref is available
  useEffect(() => {
    if (position && panelRef.current) {
      panelRef.current.style.left = `${position.x}px`;
      panelRef.current.style.top = `${position.y}px`;
    }
  }, [position]);

  // Update position when panel size changes (logs opened/closed)
  useEffect(() => {
    if (!position || !panelRef.current) return;

    const panelWidth = isCollapsed ? 48 : 320;
    const panelHeight = isCollapsed ? 48 : (showLogs ? 500 : 200);
    const maxX = window.innerWidth - panelWidth;
    const maxY = window.innerHeight - panelHeight;
    
    // Adjust position if panel would go off-screen
    const newX = Math.min(position.x, maxX);
    const newY = Math.min(position.y, maxY);
    
    if (newX !== position.x || newY !== position.y) {
      if (panelRef.current) {
        panelRef.current.style.left = `${newX}px`;
        panelRef.current.style.top = `${newY}px`;
      }
      setPosition({ x: newX, y: newY });
    }
  }, [position, isCollapsed, showLogs]);

  // Update position on window resize
  useEffect(() => {
    if (!position || !panelRef.current) return;

    const handleResize = () => {
      const panelWidth = isCollapsed ? 48 : 320;
      const panelHeight = isCollapsed ? 48 : (showLogs ? 500 : 200);
      const maxX = window.innerWidth - panelWidth;
      const maxY = window.innerHeight - panelHeight;
      
      const newX = Math.min(position.x, maxX);
      const newY = Math.min(position.y, maxY);
      
      if (panelRef.current) {
        panelRef.current.style.left = `${newX}px`;
        panelRef.current.style.top = `${newY}px`;
      }
      setPosition({ x: newX, y: newY });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [position, isCollapsed, showLogs]);

  // Listen to real-time model status updates via WebSocket
  useWebSocketEvent<{ model_id?: string; model_name?: string; model_path?: string; model_info?: any }>('model_loaded', (payload) => {
    setIsModelLoading(false);
    setModelLoaded(true);
    const modelName = payload.model_name || payload.model_path || payload.model_info?.model_name || 'Unknown';
    setModelName(modelName);
  });

  useWebSocketEvent('model_unloaded', () => {
    setIsModelLoading(false);
    setModelLoaded(false);
    setModelName('');
  });

  // Listen to debug info updates for comprehensive model status
  useWebSocketEvent<{ model?: { loaded?: boolean; current_model?: string } }>('debug_info_updated', (payload) => {
    if (payload.model) {
      setModelLoaded(payload.model.loaded || false);
      if (payload.model.current_model) {
        setModelName(payload.model.current_model);
      }
      setIsModelLoading(false);
    }
  });

  // Listen to service status changes for model loading state
  useWebSocketEvent('service_status_changed', (payload: any) => {
    if (payload && typeof payload === 'object' && 'llm' in payload) {
      const llmStatus = payload.llm;
      if (llmStatus) {
        const isReady = llmStatus.status === 'ready';
        setModelLoaded(isReady);
        // If status changed from ready to not ready, might be loading
        if (!isReady && modelLoaded) {
          setIsModelLoading(true);
        } else if (isReady) {
          setIsModelLoading(false);
        }
      }
    }
  });

  // Check model status - use service status instead of debug endpoint to avoid logging
  useEffect(() => {
    const checkModel = () => {
      // Use LLM service status instead of debug endpoint to avoid debug endpoint access logs
      const llmStatus = statuses?.llm;
      const isReady = llmStatus?.status === 'ready';
      setModelLoaded(isReady);
      // If status is not ready and we thought it was loaded, might be loading
      if (!isReady && modelLoaded) {
        setIsModelLoading(true);
      } else if (isReady) {
        setIsModelLoading(false);
      }
      // Model name will be shown from settings context if available
      setModelName('');
    };

    checkModel();
    // Check less frequently to reduce API calls
    const interval = setInterval(checkModel, 10000);
    return () => clearInterval(interval);
  }, [statuses, modelLoaded]);

  const sttStatus = statuses?.stt?.status;
  const llmStatus = statuses?.llm?.status;
  const ttsStatuses = statuses?.tts;
  const anyTTSReady = ttsStatuses?.piper?.status === 'ready' || 
                      ttsStatuses?.kokoro?.status === 'ready' || 
                      ttsStatuses?.chatterbox?.status === 'ready';

  const getStatusIcon = (status: 'ready' | 'offline' | 'error' | undefined, isActive: boolean = false) => {
    if (isActive) {
      return <Loader2 size={12} className="animate-spin text-blue-500" />;
    }
    if (status === 'ready') {
      return <CheckCircle2 size={12} className="text-green-500" />;
    }
    if (status === 'error') {
      return <XCircle size={12} className="text-red-500" />;
    }
    return <AlertCircle size={12} className="text-yellow-500" />;
  };

  const getStatusText = (status: 'ready' | 'offline' | 'error' | undefined) => {
    if (status === 'ready') return 'Ready';
    if (status === 'error') return 'Error';
    return 'Offline';
  };

  // Collect and filter backend logs, especially model-loading related
  // Filter out debug endpoint access logs
  const allBackendLogs = apiLogs
    .filter(apiLog => !apiLog.url.includes('/api/debug'))
    .flatMap(apiLog => 
      (apiLog.backendLogs || [])
        .filter(log => {
          // Filter out logs about accessing debug endpoint
          const message = log.message.toLowerCase();
          const logger = log.logger.toLowerCase();
          return !message.includes('debug') && !logger.includes('debug');
        })
        .map(log => ({
          log,
          requestUrl: apiLog.url,
          requestTime: apiLog.timestamp,
        }))
    )
    .sort((a, b) => b.log.timestamp - a.log.timestamp);

  // Check if there's an active model loading request (no response status yet)
  useEffect(() => {
    const activeModelLoadRequests = apiLogs.filter(log => {
      const isModelLoad = log.url.includes('/models/') && log.url.includes('/load');
      const isPending = !log.responseStatus || log.responseStatus === 0;
      return isModelLoad && isPending;
    });
    
    if (activeModelLoadRequests.length > 0) {
      setIsModelLoading(true);
      // Auto-show logs when model is loading
      if (!showLogs) {
        setShowLogs(true);
      }
    } else {
      // Only set to false if we're sure it's not loading (check service status too)
      const llmStatus = statuses?.llm?.status;
      if (llmStatus === 'ready' || llmStatus === 'offline') {
        setIsModelLoading(false);
      }
    }
  }, [apiLogs, statuses, showLogs]);

  // Filter for model-loading related logs
  const modelLoadingLogs = allBackendLogs.filter(({ log, requestUrl }) => {
    const url = requestUrl.toLowerCase();
    const message = log.message.toLowerCase();
    const logger = log.logger.toLowerCase();
    
    return (
      url.includes('/models/') && url.includes('/load') ||
      message.includes('model') && (message.includes('load') || message.includes('loading')) ||
      logger.includes('llm') || logger.includes('model')
    );
  });

  // Removed auto-scroll - let user control scroll position manually
  // Auto-scrolling was hiding the header and drag handle

  // Show logs automatically when model loading is detected
  useEffect(() => {
    if (modelLoadingLogs.length > 0 && !showLogs && isModelLoading) {
      setShowLogs(true);
    }
  }, [modelLoadingLogs.length, showLogs, isModelLoading]);

  // Copy log to clipboard
  const copyLog = async (log: BackendLogEntry, requestUrl: string) => {
    const logText = `[${log.level}] ${new Date(log.timestamp * 1000).toLocaleString()}\n${log.logger}\n${log.message}${log.exception ? `\n\nException:\n${log.exception}` : ''}\n\nFrom: ${requestUrl}`;
    try {
      await navigator.clipboard.writeText(logText);
      const logId = `${log.timestamp}-${log.logger}`;
      setCopiedLogId(logId);
      setTimeout(() => setCopiedLogId(null), 2000);
    } catch (error) {
      console.error('Failed to copy log:', error);
    }
  };

  // Simple drag handlers - always attached
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDraggingRef.current || !panelRef.current) return;
      
      e.preventDefault();
      
      const panelWidth = isCollapsed ? 48 : 320;
      const panelHeight = isCollapsed ? 48 : (showLogs ? 500 : 200);
      
      // Calculate new position
      const newX = e.clientX - offsetXRef.current;
      const newY = e.clientY - offsetYRef.current;
      
      // Constrain to viewport
      const maxX = window.innerWidth - panelWidth;
      const maxY = window.innerHeight - panelHeight;
      
      const constrainedX = Math.max(0, Math.min(newX, maxX));
      const constrainedY = Math.max(0, Math.min(newY, maxY));
      
      // Update position directly via DOM for immediate response
      panelRef.current.style.left = `${constrainedX}px`;
      panelRef.current.style.top = `${constrainedY}px`;
      
      // Update state for persistence
      setPosition({ x: constrainedX, y: constrainedY });
    };

    const handleMouseUp = () => {
      if (isDraggingRef.current) {
        isDraggingRef.current = false;
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
      }
    };

    // Always attach listeners
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      isDraggingRef.current = false;
    };
  }, [isCollapsed, showLogs]);

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    // Don't drag if clicking on buttons
    const target = e.target as HTMLElement;
    if (target.closest('button') && !target.closest('[data-drag-handle]')) {
      return;
    }
    
    if (!panelRef.current) return;
    
    e.preventDefault();
    e.stopPropagation();
    
    const rect = panelRef.current.getBoundingClientRect();
    startXRef.current = e.clientX;
    startYRef.current = e.clientY;
    offsetXRef.current = e.clientX - rect.left;
    offsetYRef.current = e.clientY - rect.top;
    
    isDraggingRef.current = true;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'grabbing';
  };

  // Don't render until position is initialized to avoid hydration mismatch
  if (position === null) {
    return null;
  }

  return (
    <div
      ref={panelRef}
      className={cn(
        "fixed z-[9999] select-none",
        isCollapsed ? "w-12 h-12" : showLogs ? "w-80" : "w-64"
      )}
      style={{ 
        left: `${position.x}px`,
        top: `${position.y}px`,
        pointerEvents: 'auto',
      }}
    >
      <div
        className={cn(
          "bg-background border-2 border-primary/50 rounded shadow-2xl",
          "transition-all duration-200 overflow-hidden flex flex-col",
          isCollapsed ? "h-full" : showLogs ? "h-[500px]" : "min-h-[200px]"
        )}
      >
        {/* Header/Toggle Button */}
        <div
          onMouseDown={handleMouseDown}
          className={cn(
            "relative w-full flex items-center justify-between p-2 hover:bg-muted/50 transition-colors cursor-move",
            isCollapsed && "justify-center",
            isGenerating && "animate-pulse"
          )}
          style={{ userSelect: 'none' }}
        >
          <div className="flex items-center gap-2 flex-1">
            <GripVertical 
              size={14} 
              className="text-muted-foreground/50"
              data-drag-handle
              style={{ pointerEvents: 'none' }}
            />
            <Activity 
              size={16} 
              className={cn(
                "text-primary",
                isGenerating && "animate-spin"
              )} 
            />
            {!isCollapsed && (
              <span className="text-xs font-medium">Debug Status</span>
            )}
          </div>
          {!isCollapsed && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsCollapsed(!isCollapsed);
              }}
              className="ml-2"
              title={isCollapsed ? "Show debug status" : "Hide debug status"}
            >
              <Badge variant={isGenerating ? 'default' : 'secondary'} className="text-xs">
                {isGenerating ? 'Generating' : 'Idle'}
              </Badge>
            </button>
          )}
          {isCollapsed && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsCollapsed(!isCollapsed);
              }}
              className="absolute inset-0"
              title="Show debug status"
            />
          )}
          {isCollapsed && isGenerating && (
            <div className="absolute top-1 right-1 w-2 h-2 bg-blue-500 rounded-full animate-pulse pointer-events-none" />
          )}
        </div>

        {/* Content */}
        {!isCollapsed && (
          <div className="p-2 space-y-2 text-xs border-t border-border flex-shrink-0">
            {/* Backend Server */}
            <div className="flex items-center justify-between py-1">
              <div className="flex items-center gap-2">
                <Server size={12} className="text-muted-foreground" />
                <span>Backend</span>
              </div>
              <div className="flex items-center gap-1">
                {isChecking ? (
                  <Loader2 size={12} className="animate-spin text-blue-500" />
                ) : backendReady ? (
                  <CheckCircle2 size={12} className="text-green-500" />
                ) : (
                  <XCircle size={12} className="text-red-500" />
                )}
                <span className={cn(
                  "text-xs",
                  backendReady ? "text-green-600" : "text-red-600"
                )}>
                  {backendReady ? 'Online' : 'Offline'}
                </span>
              </div>
            </div>

            {/* Model Generation */}
            <div className="flex items-center justify-between py-1">
              <div className="flex items-center gap-2">
                <Brain size={12} className="text-muted-foreground" />
                <span>Model</span>
              </div>
              <div className="flex items-center gap-1">
                {isModelLoading ? (
                  <>
                    <Loader2 size={12} className="animate-spin text-blue-500" />
                    <span className="text-xs text-blue-600">Loading...</span>
                  </>
                ) : isGenerating ? (
                  <>
                    <Loader2 size={12} className="animate-spin text-blue-500" />
                    <span className="text-xs text-blue-600">Generating</span>
                  </>
                ) : modelLoaded ? (
                  <>
                    <CheckCircle2 size={12} className="text-green-500" />
                    <span className="text-xs text-green-600">Loaded</span>
                  </>
                ) : (
                  <>
                    <XCircle size={12} className="text-yellow-500" />
                    <span className="text-xs text-yellow-600">Not Loaded</span>
                  </>
                )}
              </div>
            </div>

            {/* Model Name */}
            {modelName && (
              <div className="px-2 py-0.5 text-xs text-muted-foreground truncate" title={modelName}>
                {modelName}
              </div>
            )}

            {/* LLM Service */}
            <div className="flex items-center justify-between py-1">
              <div className="flex items-center gap-2">
                <Brain size={12} className="text-muted-foreground" />
                <span>LLM Service</span>
              </div>
              <div className="flex items-center gap-1">
                {getStatusIcon(llmStatus)}
                <span className={cn(
                  "text-xs",
                  llmStatus === 'ready' ? "text-green-600" : "text-red-600"
                )}>
                  {getStatusText(llmStatus)}
                </span>
              </div>
            </div>

            {/* STT Service */}
            <div className="flex items-center justify-between py-1">
              <div className="flex items-center gap-2">
                <Mic size={12} className="text-muted-foreground" />
                <span>STT</span>
              </div>
              <div className="flex items-center gap-1">
                {getStatusIcon(sttStatus)}
                <span className={cn(
                  "text-xs",
                  sttStatus === 'ready' ? "text-green-600" : "text-red-600"
                )}>
                  {getStatusText(sttStatus)}
                </span>
              </div>
            </div>

            {/* TTS Service */}
            <div className="flex items-center justify-between py-1">
              <div className="flex items-center gap-2">
                <Volume2 size={12} className="text-muted-foreground" />
                <span>TTS</span>
              </div>
              <div className="flex items-center gap-1">
                {getStatusIcon(anyTTSReady ? 'ready' : 'offline')}
                <span className={cn(
                  "text-xs",
                  anyTTSReady ? "text-green-600" : "text-red-600"
                )}>
                  {anyTTSReady ? 'Ready' : 'Offline'}
                </span>
              </div>
            </div>

            {/* Live Logs Toggle */}
            <div className="border-t border-border pt-2 mt-2">
              <button
                onClick={() => setShowLogs(!showLogs)}
                className="w-full flex items-center justify-between py-1 px-2 hover:bg-muted/50 rounded transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Terminal size={12} className="text-muted-foreground" />
                  <span className="text-xs">Live Logs</span>
                  {modelLoadingLogs.length > 0 && (
                    <Badge variant="secondary" className="text-xs h-4 px-1">
                      {modelLoadingLogs.length}
                    </Badge>
                  )}
                </div>
                {showLogs ? (
                  <X size={12} className="text-muted-foreground" />
                ) : (
                  <span className="text-xs text-muted-foreground">▶</span>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Live Logs Viewer */}
        {showLogs && (
          <div className="border-t border-border bg-muted/30 flex flex-col flex-1 min-h-0">
            <div className="p-2 border-b border-border flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-2">
                <Terminal size={12} className="text-muted-foreground" />
                <span className="text-xs font-medium">Backend Logs</span>
                <Badge variant="secondary" className="text-xs h-4 px-1">
                  {allBackendLogs.length}
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                {allBackendLogs.length > 0 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      clearLogs();
                    }}
                    className="text-muted-foreground hover:text-destructive transition-colors"
                    title="Clear all logs"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
                <button
                  onClick={() => setShowLogs(false)}
                  className="text-muted-foreground hover:text-foreground"
                  title="Close logs"
                >
                  <X size={12} />
                </button>
              </div>
            </div>
            <div 
              className="flex-1 overflow-y-auto min-h-0"
              onMouseDown={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <div className="p-2 space-y-1">
                {allBackendLogs.length === 0 ? (
                  <div className="text-xs text-muted-foreground text-center py-4">
                    No backend logs yet. Enable Developer Mode in Debug Panel to see logs.
                  </div>
                ) : (
                  allBackendLogs.slice(0, 100).map(({ log, requestUrl }, idx) => {
                    const isModelLoading = modelLoadingLogs.some(ml => ml.log.timestamp === log.timestamp);
                    const logColor = 
                      log.level === 'ERROR' || log.level === 'CRITICAL' ? 'text-red-500' :
                      log.level === 'WARNING' ? 'text-yellow-500' :
                      log.level === 'INFO' ? 'text-blue-500' :
                      'text-muted-foreground';
                    
                    const logId = `${log.timestamp}-${log.logger}-${idx}`;
                    const isCopied = copiedLogId === logId;
                    
                    return (
                      <div
                        key={logId}
                        className={cn(
                          "text-xs p-1.5 rounded border-l-2 group hover:bg-muted/30 transition-colors cursor-pointer",
                          isModelLoading && "bg-primary/5 border-primary/50",
                          !isModelLoading && "border-transparent"
                        )}
                        style={{
                          borderLeftColor: 
                            log.level === 'ERROR' || log.level === 'CRITICAL' ? 'rgb(239, 68, 68)' :
                            log.level === 'WARNING' ? 'rgb(251, 191, 36)' :
                            log.level === 'INFO' ? 'rgb(59, 130, 246)' :
                            'transparent'
                        }}
                        onClick={() => copyLog(log, requestUrl)}
                        title="Click to copy log"
                      >
                        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                          <span className={cn("text-xs font-mono", logColor)}>
                            [{log.level}]
                          </span>
                          <span className="text-muted-foreground text-xs">
                            {new Date(log.timestamp * 1000).toLocaleTimeString()}
                          </span>
                          {isModelLoading && (
                            <Badge variant="outline" className="text-xs h-4 px-1">
                              Model
                            </Badge>
                          )}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              copyLog(log, requestUrl);
                            }}
                            className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Copy log"
                          >
                            {isCopied ? (
                              <Check size={12} className="text-green-500" />
                            ) : (
                              <Copy size={12} className="text-muted-foreground hover:text-foreground" />
                            )}
                          </button>
                        </div>
                        <div className="break-words text-xs">{log.message}</div>
                        {log.exception && (
                          <details className="mt-1" onClick={(e) => e.stopPropagation()}>
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground text-xs">
                              Exception
                            </summary>
                            <pre className="mt-1 p-1 bg-background rounded text-xs overflow-x-auto font-mono max-h-32 overflow-y-auto">
                              {log.exception}
                            </pre>
                          </details>
                        )}
                        <div className="text-muted-foreground text-xs mt-0.5 truncate" title={requestUrl}>
                          From: {requestUrl}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
