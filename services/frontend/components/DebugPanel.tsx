'use client';

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Trash2, Code, Bug, Search, Filter, X, Copy, Check, Clipboard } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api';
import { formatBytes } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { useDeveloperMode, BackendLogEntry, ApiLogEntry } from '@/contexts/DeveloperModeContext';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';

interface DebugPanelProps {
  onClose: () => void;
  onWidthChange?: (width: number) => void;
}

interface DebugInfo {
  services?: Record<string, unknown>;
  model?: {
    loaded?: boolean;
    current_model?: string;
    gpu_layers?: number;
  };
  memory?: {
    conversation_count?: number;
    message_count?: number;
    db_size_bytes?: number;
  };
  conversations?: {
    active_count?: number;
  };
}

export default function DebugPanel({ onClose: _onClose, onWidthChange: _onWidthChange }: DebugPanelProps) { // eslint-disable-line @typescript-eslint/no-unused-vars
  const [debugInfo, setDebugInfo] = useState<DebugInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('system');
  const { enabled: devModeEnabled, toggle: toggleDevMode, logs: apiLogs, clearLogs } = useDeveloperMode();
  const [backendLogSearch, setBackendLogSearch] = useState('');
  const [backendLogLevelFilter, setBackendLogLevelFilter] = useState<string>('ALL');
  const [copiedLogId, setCopiedLogId] = useState<string | null>(null);
  const [copiedRequestId, setCopiedRequestId] = useState<string | null>(null);

  const loadDebugInfo = useCallback(async () => {
    try {
      const info = await api.getDebugInfo() as DebugInfo;
      setDebugInfo(info);
      setLoading(false);
    } catch (error) {
      console.error('Error loading debug info:', error);
      setLoading(false);
      setDebugInfo(null);
    }
  }, []);

  // Load once on mount, then listen to WebSocket updates
  useEffect(() => {
      loadDebugInfo();
  }, [loadDebugInfo]);
  
  // Listen to real-time debug info updates via WebSocket
  useWebSocketEvent<DebugInfo>('debug_info_updated', (payload) => {
    setDebugInfo(payload);
    setLoading(false);
  });
  
  // Also listen to model loaded/unloaded events for immediate updates
  useWebSocketEvent('model_loaded', () => {
    loadDebugInfo();
  });
  
  useWebSocketEvent('model_unloaded', () => {
    loadDebugInfo();
  });
  
  // Listen to service status changes
  useWebSocketEvent('service_status_changed', () => {
    loadDebugInfo();
  });

  const formatTimestamp = (timestamp: number) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return 'N/A';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

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

  // Copy full request/response stack to clipboard
  const copyFullRequestStack = async (log: ApiLogEntry) => {
    try {
      let stackText = `=== API Request/Response Stack ===\n\n`;
      stackText += `Method: ${log.method || 'GET'}\n`;
      stackText += `URL: ${log.url}\n`;
      stackText += `Status: ${log.responseStatus || 'N/A'}\n`;
      stackText += `Duration: ${formatDuration(log.duration)}\n`;
      stackText += `Timestamp: ${formatTimestamp(log.timestamp)}\n\n`;
      
      if (log.error) {
        stackText += `=== Error ===\n${log.error}\n\n`;
      }
      
      if (log.requestBody) {
        stackText += `=== Request Body ===\n${JSON.stringify(log.requestBody, null, 2)}\n\n`;
      }
      
      if (log.responseBody) {
        stackText += `=== Response Body ===\n${JSON.stringify(log.responseBody, null, 2)}\n\n`;
      }
      
      if (log.backendLogs && log.backendLogs.length > 0) {
        stackText += `=== Backend Logs (${log.backendLogs.length}) ===\n`;
        log.backendLogs.forEach((backendLog, idx) => {
          stackText += `\n[${idx + 1}] [${backendLog.level}] ${new Date(backendLog.timestamp * 1000).toLocaleString()}\n`;
          stackText += `Logger: ${backendLog.logger}\n`;
          stackText += `Message: ${backendLog.message}\n`;
          if (backendLog.exception) {
            stackText += `Exception:\n${backendLog.exception}\n`;
          }
        });
      }
      
      await navigator.clipboard.writeText(stackText);
      setCopiedRequestId(log.id);
      setTimeout(() => setCopiedRequestId(null), 2000);
    } catch (error) {
      console.error('Failed to copy request stack:', error);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-3">
          <Bug size={20} className="text-primary" />
          <h2 className="text-lg font-semibold">Developer Mode</h2>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">API Logging</span>
            <Switch checked={devModeEnabled} onCheckedChange={toggleDevMode} />
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={loadDebugInfo}
            className="h-8 w-8"
            title="Refresh"
          >
            <RefreshCw size={20} />
          </Button>
        </div>
      </div>
      
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
        <div className="px-4 pt-4 border-b border-border flex-shrink-0">
          <TabsList>
            <TabsTrigger value="system">System Info</TabsTrigger>
            <TabsTrigger value="api" className="flex items-center gap-2">
              <Code size={14} />
              API Logs
              {apiLogs.length > 0 && (
                <Badge variant="secondary" className="ml-1">
                  {apiLogs.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="backend-logs" className="flex items-center gap-2">
              <Bug size={14} />
              Backend Logs
              {(() => {
                const totalBackendLogs = apiLogs.reduce((sum, log) => sum + (log.backendLogs?.length || 0), 0);
                return totalBackendLogs > 0 ? (
                  <Badge variant="secondary" className="ml-1">
                    {totalBackendLogs}
                  </Badge>
                ) : null;
              })()}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="system" className="flex-1 min-h-0 mt-0">
          <ScrollArea className="h-full">
            <div className="p-4 space-y-4 text-sm">
        {loading && (
          <Skeleton className="h-20 w-full" />
        )}
        {!loading && debugInfo && (
          <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Services</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 font-mono text-xs">
                {Object.entries((debugInfo?.services || {})).map(([key, value]: [string, unknown]) => {
                  const serviceValue = value as { initialized?: boolean; status?: string; provider?: string; model_size?: string; backends?: Record<string, unknown> } | boolean;
                  const isInitialized = typeof serviceValue === 'boolean' ? serviceValue : serviceValue?.initialized;
                  const status =
                    typeof serviceValue === 'object' && serviceValue !== null
                      ? serviceValue.status
                      : isInitialized
                        ? 'initialized'
                        : 'not_initialized';
                  const statusVariant =
                    status === 'ready' ? 'default' : status === 'initialized' ? 'secondary' : 'destructive';

                  return (
                    <div key={key} className="border-b border-border pb-2 last:border-0">
                      <div className="flex items-center justify-between">
                        <span>{key}:</span>
                        <Badge variant={statusVariant}>
                          {status === 'ready'
                            ? '✓ Ready'
                            : status === 'initialized'
                              ? '○ Initialized'
                              : '✗ Not Initialized'}
                        </Badge>
                      </div>
                      {typeof serviceValue === 'object' && serviceValue !== null && (
                        <>
                          {serviceValue.provider && (
                            <div className="block text-muted-foreground text-xs mt-1">
                              Provider: {serviceValue.provider}
                            </div>
                          )}
                          {serviceValue.model_size && (
                            <div className="block text-muted-foreground text-xs mt-1">
                              Model: {serviceValue.model_size}
                            </div>
                          )}
                        </>
                      )}
                      {typeof serviceValue === 'object' && serviceValue !== null && serviceValue.backends && typeof serviceValue.backends === 'object' && !Array.isArray(serviceValue.backends) && (
                        <div className="block text-muted-foreground text-xs mt-1">
                          <div className="mt-1">Backends:</div>
                          {Object.entries(serviceValue.backends).map(([backendName, backendInfo]: [string, unknown]) => {
                            const backend = backendInfo as { is_ready?: boolean; is_current?: boolean; error_message?: string };
                            return (
                              <div key={backendName} className="ml-2">
                                {backendName}: {backend.is_ready ? '✓' : '✗'}
                                {backend.is_current && <span className="inline"> (current)</span>}
                                {backend.error_message && (
                                  <div className="block text-destructive text-xs ml-4">
                                    {backend.error_message}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Model</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="font-mono text-xs space-y-1">
                <div>Loaded: {debugInfo?.model?.loaded ? 'Yes' : 'No'}</div>
                <div className={cn("hidden", debugInfo?.model?.current_model && "block")}>
                  Model: {debugInfo?.model?.current_model || 'Unknown'}
                </div>
                <div className={cn("hidden", debugInfo?.model?.gpu_layers !== undefined && "block")}>
                  GPU Layers: {debugInfo?.model?.gpu_layers || 0}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Memory</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="font-mono text-xs space-y-1">
                <div>Conversations: {debugInfo?.memory?.conversation_count || 0}</div>
                <div>Messages: {debugInfo?.memory?.message_count || 0}</div>
                <div className={cn("hidden", debugInfo?.memory?.db_size_bytes && "block")}>
                  DB Size: {formatBytes(debugInfo?.memory?.db_size_bytes || 0)}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Conversations</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="font-mono text-xs">
                <div>Active: {debugInfo?.conversations?.active_count || 0}</div>
              </div>
            </CardContent>
          </Card>
          </div>
        )}
        {!loading && !debugInfo && (
          <p className="text-muted-foreground">No debug info available</p>
        )}
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="api" className="flex-1 min-h-0 mt-0">
          <div className="h-full flex flex-col">
            <div className="px-4 py-2 border-b border-border flex items-center justify-between flex-shrink-0">
              <div className="text-xs text-muted-foreground">
                {apiLogs.length} request{apiLogs.length !== 1 ? 's' : ''} logged
              </div>
              {apiLogs.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearLogs}
                  className="h-7 text-xs"
                >
                  <Trash2 size={14} className="mr-1" />
                  Clear
                </Button>
              )}
            </div>
            <ScrollArea className="flex-1">
              <div className="p-4 space-y-2">
                {!devModeEnabled && (
                  <div className="text-center py-8 text-muted-foreground">
                    <Code size={48} className="mx-auto mb-3 opacity-20" />
                    <p>API logging is disabled</p>
                    <p className="text-xs mt-1">Enable it above to see API requests and responses</p>
                  </div>
                )}
                {devModeEnabled && apiLogs.length === 0 && (
                  <div className="text-center py-8 text-muted-foreground">
                    <Code size={48} className="mx-auto mb-3 opacity-20" />
                    <p>No API requests logged yet</p>
                    <p className="text-xs mt-1">Make some API calls to see them here</p>
                  </div>
                )}
                {devModeEnabled && apiLogs
                  .filter(log => !log.url.includes('/api/debug'))
                  .map((log) => {
                    const hasBackendLogs = log.backendLogs && log.backendLogs.length > 0;
                    const errorLogs = hasBackendLogs && log.backendLogs ? log.backendLogs.filter(l => l.level === 'ERROR' || l.level === 'CRITICAL') : [];
                    const isCopied = copiedRequestId === log.id;
                    const isModelLoad = log.url.includes('/models/') && log.url.includes('/load');
                    
                    // For model loading, bundle logs into summary
                    let logSummary = null;
                    if (isModelLoad && hasBackendLogs && log.backendLogs) {
                      const infoLogs = log.backendLogs.filter(l => l.level === 'INFO').length;
                      const warningLogs = log.backendLogs.filter(l => l.level === 'WARNING').length;
                      const errorCount = errorLogs.length;
                      const totalLogs = log.backendLogs.length;
                      
                      // Extract key messages
                      const keyMessages: string[] = [];
                      log.backendLogs.forEach(l => {
                        const msg = l.message.toLowerCase();
                        if (msg.includes('loading') || msg.includes('loaded') || msg.includes('starting') || 
                            msg.includes('server') || msg.includes('model') || msg.includes('success')) {
                          if (!keyMessages.some(m => m.toLowerCase() === l.message.toLowerCase())) {
                            keyMessages.push(l.message);
                          }
                        }
                      });
                      
                      logSummary = {
                        total: totalLogs,
                        info: infoLogs,
                        warnings: warningLogs,
                        errors: errorCount,
                        keyMessages: keyMessages.slice(0, 5), // Top 5 key messages
                      };
                    }
                    
                    return (
                      <Card key={log.id} className="text-xs hover:bg-muted/50 transition-colors group">
                        <CardContent className="p-3">
                          <div className="flex items-start justify-between mb-2 flex-wrap gap-2">
                            <div className="flex items-center gap-2 flex-wrap flex-1">
                              <Badge
                                variant={
                                  log.error
                                    ? 'destructive'
                                    : log.responseStatus && log.responseStatus >= 400
                                    ? 'destructive'
                                    : log.responseStatus && log.responseStatus >= 200 && log.responseStatus < 300
                                    ? 'default'
                                    : 'secondary'
                                }
                                className="font-mono shrink-0"
                              >
                                {log.method || 'GET'}
                              </Badge>
                              <span className="font-mono text-muted-foreground shrink-0">
                                {log.responseStatus || '...'}
                              </span>
                              {log.duration && (
                                <span className="text-muted-foreground shrink-0">
                                  {formatDuration(log.duration)}
                                </span>
                              )}
                              {hasBackendLogs && log.backendLogs && (
                                <Badge variant="outline" className="shrink-0">
                                  {isModelLoad && logSummary ? (
                                    <>
                                      {logSummary.total} logs
                                      {logSummary.errors > 0 && ` (${logSummary.errors} error${logSummary.errors !== 1 ? 's' : ''})`}
                                      {logSummary.warnings > 0 && `, ${logSummary.warnings} warning${logSummary.warnings !== 1 ? 's' : ''}`}
                                    </>
                                  ) : (
                                    <>
                                      {log.backendLogs.length} log{log.backendLogs.length !== 1 ? 's' : ''}
                                      {errorLogs.length > 0 && ` (${errorLogs.length} error${errorLogs.length !== 1 ? 's' : ''})`}
                                    </>
                                  )}
                                </Badge>
                              )}
                            </div>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => copyFullRequestStack(log)}
                                className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-foreground"
                                title="Copy full request/response stack"
                              >
                                {isCopied ? (
                                  <Check size={14} className="text-green-500" />
                                ) : (
                                  <Clipboard size={14} />
                                )}
                              </button>
                              <span className="text-muted-foreground text-xs shrink-0">
                                {formatTimestamp(log.timestamp)}
                              </span>
                            </div>
                          </div>
                        <div className="font-mono text-xs break-all text-muted-foreground mb-2">
                          {log.url}
                        </div>
                        {log.error && (
                          <div className="mt-2 p-2 bg-destructive/10 border border-destructive/20 rounded text-destructive text-xs">
                            Error: {log.error}
                          </div>
                        )}
                        {hasBackendLogs && log.backendLogs && errorLogs.length > 0 && (
                          <div className="mt-2 p-2 bg-destructive/10 border border-destructive/20 rounded text-destructive text-xs">
                            <div className="font-semibold mb-1">Backend Errors ({errorLogs.length}):</div>
                            {errorLogs.slice(0, 2).map((backendLog, idx) => (
                              <div key={idx} className="mt-1">
                                <span className="font-mono text-xs">[{backendLog.level}]</span> {backendLog.message}
                              </div>
                            ))}
                            {errorLogs.length > 2 && (
                              <div className="mt-1 text-xs opacity-75">
                                ... and {errorLogs.length - 2} more error(s)
                              </div>
                            )}
                          </div>
                        )}
                        {log.requestBody && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground text-xs">
                              Request Body
                            </summary>
                            <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-x-auto max-h-40 overflow-y-auto font-mono">
                              {JSON.stringify(log.requestBody, null, 2)}
                            </pre>
                          </details>
                        )}
                        {log.responseBody && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground text-xs">
                              Response Body
                            </summary>
                            <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-x-auto max-h-60 overflow-y-auto font-mono">
                              {JSON.stringify(log.responseBody, null, 2)}
                            </pre>
                          </details>
                        )}
                        {hasBackendLogs && log.backendLogs && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground text-xs">
                              {isModelLoad && logSummary ? (
                                <>
                                  Model Loading Logs ({logSummary.total} total)
                                  {logSummary.errors > 0 && ` - ${logSummary.errors} error${logSummary.errors !== 1 ? 's' : ''}`}
                                </>
                              ) : (
                                `Backend Logs (${log.backendLogs.length})`
                              )}
                            </summary>
                            {isModelLoad && logSummary && logSummary.keyMessages.length > 0 && (
                              <div className="mt-2 p-2 bg-muted/50 rounded text-xs">
                                <div className="font-semibold mb-1">Key Steps:</div>
                                <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                                  {logSummary.keyMessages.map((msg, idx) => (
                                    <li key={idx} className="truncate" title={msg}>{msg}</li>
                                  ))}
                                </ul>
                                {logSummary.total > logSummary.keyMessages.length && (
                                  <div className="mt-1 text-xs opacity-75">
                                    ... and {logSummary.total - logSummary.keyMessages.length} more log entries
                                  </div>
                                )}
                              </div>
                            )}
                            <div className="mt-1 space-y-1 max-h-60 overflow-y-auto">
                              {log.backendLogs.map((backendLog, idx) => (
                                <div key={idx} className="p-2 bg-muted rounded text-xs border-l-2" style={{
                                  borderLeftColor: 
                                    backendLog.level === 'ERROR' || backendLog.level === 'CRITICAL' ? 'rgb(239, 68, 68)' :
                                    backendLog.level === 'WARNING' ? 'rgb(251, 191, 36)' :
                                    backendLog.level === 'INFO' ? 'rgb(59, 130, 246)' :
                                    'rgb(107, 114, 128)'
                                }}>
                                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                                    <Badge variant={
                                      backendLog.level === 'ERROR' || backendLog.level === 'CRITICAL' ? 'destructive' :
                                      backendLog.level === 'WARNING' ? 'default' :
                                      'secondary'
                                    } className="text-xs shrink-0">
                                      {backendLog.level}
                                    </Badge>
                                    <span className="text-muted-foreground text-xs shrink-0">
                                      {new Date(backendLog.timestamp * 1000).toLocaleTimeString()}
                                    </span>
                                    <span className="text-muted-foreground text-xs font-mono truncate max-w-[150px]">
                                      {backendLog.logger}
                                    </span>
                                  </div>
                                  <div className="break-words text-sm">{backendLog.message}</div>
                                  {backendLog.exception && (
                                    <details className="mt-1">
                                      <summary className="cursor-pointer text-muted-foreground hover:text-foreground text-xs">
                                        Exception
                                      </summary>
                                      <pre className="mt-1 p-2 bg-background rounded text-xs overflow-x-auto font-mono">
                                        {backendLog.exception}
                                      </pre>
                                    </details>
                                  )}
                                </div>
                              ))}
                            </div>
                          </details>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </ScrollArea>
          </div>
        </TabsContent>

        <TabsContent value="backend-logs" className="flex-1 min-h-0 mt-0">
          <div className="h-full flex flex-col">
            <div className="px-4 py-2 border-b border-border flex flex-col gap-2 flex-shrink-0">
              <div className="flex items-center justify-between">
                <div className="text-xs text-muted-foreground">
                  {(() => {
                    const totalBackendLogs = apiLogs.reduce((sum, log) => sum + (log.backendLogs?.length || 0), 0);
                    return `${totalBackendLogs} backend log${totalBackendLogs !== 1 ? 's' : ''} from ${apiLogs.filter(log => log.backendLogs && log.backendLogs.length > 0).length} request${apiLogs.filter(log => log.backendLogs && log.backendLogs.length > 0).length !== 1 ? 's' : ''}`;
                  })()}
                </div>
                {apiLogs.some(log => log.backendLogs && log.backendLogs.length > 0) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearLogs}
                    className="h-7 text-xs"
                  >
                    <Trash2 size={14} className="mr-1" />
                    Clear
                  </Button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search logs..."
                    value={backendLogSearch}
                    onChange={(e) => setBackendLogSearch(e.target.value)}
                    className="pl-8 h-8 text-xs"
                  />
                  {backendLogSearch && (
                    <button
                      onClick={() => setBackendLogSearch('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
                <select
                  value={backendLogLevelFilter}
                  onChange={(e) => setBackendLogLevelFilter(e.target.value)}
                  className="h-8 px-2 text-xs bg-background border border-border rounded"
                >
                  <option value="ALL">All Levels</option>
                  <option value="DEBUG">Debug</option>
                  <option value="INFO">Info</option>
                  <option value="WARNING">Warning</option>
                  <option value="ERROR">Error</option>
                  <option value="CRITICAL">Critical</option>
                </select>
              </div>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-4 space-y-2">
                {(() => {
                  // Collect all backend logs
                  const allBackendLogs: Array<{ log: BackendLogEntry; requestId: string; requestUrl: string }> = [];
                  apiLogs.forEach(apiLog => {
                    if (apiLog.backendLogs) {
                      apiLog.backendLogs.forEach(backendLog => {
                        allBackendLogs.push({
                          log: backendLog,
                          requestId: apiLog.id,
                          requestUrl: apiLog.url
                        });
                      });
                    }
                  });
                  
                  // Sort by timestamp (newest first)
                  allBackendLogs.sort((a, b) => b.log.timestamp - a.log.timestamp);
                  
                  // Apply filters
                  const filteredLogs = allBackendLogs.filter(entry => {
                    // Level filter
                    if (backendLogLevelFilter !== 'ALL' && entry.log.level !== backendLogLevelFilter) {
                      return false;
                    }
                    // Search filter
                    if (backendLogSearch) {
                      const searchLower = backendLogSearch.toLowerCase();
                      return (
                        entry.log.message.toLowerCase().includes(searchLower) ||
                        entry.log.logger.toLowerCase().includes(searchLower) ||
                        entry.requestUrl.toLowerCase().includes(searchLower) ||
                        (entry.log.exception && entry.log.exception.toLowerCase().includes(searchLower))
                      );
                    }
                    return true;
                  });

                  if (allBackendLogs.length === 0) {
                    return (
                      <div className="text-center py-8 text-muted-foreground">
                        <Bug size={48} className="mx-auto mb-3 opacity-20" />
                        <p>No backend logs available</p>
                        <p className="text-xs mt-1">Backend logs will appear here when developer mode is enabled</p>
                      </div>
                    );
                  }
                  
                  if (filteredLogs.length === 0) {
                    return (
                      <div className="text-center py-8 text-muted-foreground">
                        <Filter size={48} className="mx-auto mb-3 opacity-20" />
                        <p>No logs match your filters</p>
                        <p className="text-xs mt-1">Try adjusting your search or level filter</p>
                      </div>
                    );
                  }

                  return filteredLogs.map((entry, idx) => {
                    const logId = `${entry.log.timestamp}-${entry.log.logger}-${idx}`;
                    const isCopied = copiedLogId === logId;
                    
                    return (
                      <Card 
                        key={`${entry.requestId}-${idx}`} 
                        className="text-xs hover:bg-muted/50 transition-colors group cursor-pointer"
                        onClick={() => copyLog(entry.log, entry.requestUrl)}
                        title="Click to copy log"
                      >
                        <CardContent className="p-3">
                          <div className="flex items-start gap-2 mb-2 flex-wrap">
                            <Badge variant={
                              entry.log.level === 'ERROR' || entry.log.level === 'CRITICAL' ? 'destructive' :
                              entry.log.level === 'WARNING' ? 'default' :
                              'secondary'
                            } className="text-xs shrink-0">
                              {entry.log.level}
                            </Badge>
                            <span className="text-muted-foreground text-xs shrink-0">
                              {new Date(entry.log.timestamp * 1000).toLocaleTimeString()}
                            </span>
                            <span className="text-muted-foreground text-xs font-mono truncate max-w-[200px]">
                              {entry.log.logger}
                            </span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                copyLog(entry.log, entry.requestUrl);
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
                          <div className="break-words mb-2 text-sm">{entry.log.message}</div>
                          <div className="text-muted-foreground text-xs font-mono mb-2 truncate">
                            From: {entry.requestUrl}
                          </div>
                          {entry.log.exception && (
                            <details className="mt-2" onClick={(e) => e.stopPropagation()}>
                              <summary className="cursor-pointer text-muted-foreground hover:text-foreground text-xs">
                                Exception Traceback
                              </summary>
                              <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-x-auto max-h-60 overflow-y-auto font-mono">
                                {entry.log.exception}
                              </pre>
                            </details>
                          )}
                        </CardContent>
                      </Card>
                    );
                  });
                })()}
              </div>
            </ScrollArea>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
