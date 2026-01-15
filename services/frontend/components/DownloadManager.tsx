'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';
import {
  Download,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  Trash2,
  RefreshCw,
  X,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import { formatBytes, formatTime, formatDate } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';

interface DownloadItem {
  id: string;
  repo_id: string;
  filename: string;
  status: 'pending' | 'downloading' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  bytes_downloaded: number;
  total_bytes: number;
  speed_bps: number;
  speed_mbps: number;
  error?: string;
  started_at?: string;
  completed_at?: string;
  model_path?: string;
  eta_seconds?: number;
}

interface DownloadsResponse {
  active: DownloadItem[];
  history: DownloadItem[];
  active_count: number;
}

interface DownloadManagerProps {
  isOpen: boolean;
  onClose: () => void;
  onDownloadComplete?: () => void;
}

export default function DownloadManager({
  isOpen,
  onClose,
  onDownloadComplete,
}: DownloadManagerProps) {
  const { showConfirm } = useToast();
  const [downloads, setDownloads] = useState<DownloadsResponse>({
    active: [],
    history: [],
    active_count: 0,
  });
  const [loading, setLoading] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const processedCompletedIds = useRef<Set<string>>(new Set());

  const loadDownloads = useCallback(async () => {
    try {
      const data = (await api.listDownloads()) as DownloadsResponse;
      
      // Debug logging
      console.log('[DownloadManager] Received download data:', {
        activeCount: data.active_count,
        activeDownloads: data.active.map(d => ({
          id: d.id,
          filename: d.filename,
          status: d.status,
          progress: d.progress,
          bytes_downloaded: d.bytes_downloaded,
          total_bytes: d.total_bytes,
          speed_mbps: d.speed_mbps,
          speed_bps: d.speed_bps,
          eta_seconds: d.eta_seconds
        }))
      });
      
      // Check if any download just completed (status changed to 'completed' and we haven't processed it yet)
      const newlyCompleted = data.active.filter(
        (d) => d.status === 'completed' && !processedCompletedIds.current.has(d.id)
      );
      
      setDownloads(data);

      // Trigger discovery for newly completed downloads
      if (newlyCompleted.length > 0 && onDownloadComplete) {
        // Mark these as processed
        newlyCompleted.forEach(d => processedCompletedIds.current.add(d.id));
        onDownloadComplete();
      }
    } catch (error) {
      console.error('Error loading downloads:', error);
    } finally {
      setLoading(false);
    }
  }, [onDownloadComplete]);

  // Subscribe to WebSocket events for real-time download updates
  useWebSocketEvent('download_progress', (payload) => {
    if (payload && isOpen) {
      setDownloads((prev) => {
        const active = [...(prev.active || [])];
        const index = active.findIndex((d) => d.id === payload.download_id);
        if (index >= 0) {
          active[index] = { ...active[index], ...payload };
        } else {
          // New download
          active.push({
            id: payload.download_id,
            repo_id: payload.repo_id,
            filename: payload.filename,
            status: payload.status,
            progress: payload.progress,
            bytes_downloaded: payload.bytes_downloaded,
            total_bytes: payload.total_bytes,
            speed_bps: payload.speed_bps,
            speed_mbps: payload.speed_mbps,
            eta_seconds: payload.eta_seconds,
          });
        }
        return { ...prev, active, active_count: active.length };
      });
    }
  });

  useWebSocketEvent('download_completed', (payload) => {
    if (payload && isOpen) {
      setDownloads((prev) => {
        const active = prev.active.filter((d) => d.id !== payload.download_id);
        const history = [...(prev.history || []), {
          id: payload.download_id,
          repo_id: payload.repo_id,
          filename: payload.filename,
          status: 'completed' as const,
          progress: 100,
          bytes_downloaded: payload.total_bytes,
          total_bytes: payload.total_bytes,
          speed_bps: 0,
          speed_mbps: 0,
          model_path: payload.model_path,
        }];
        return { ...prev, active, history, active_count: active.length };
      });
      
      if (onDownloadComplete) {
        onDownloadComplete();
      }
    }
  });

  useEffect(() => {
    if (isOpen) {
      // Initial load only - then rely on WebSocket events
      loadDownloads();
    }
  }, [isOpen, loadDownloads]);

  const handleCancel = async (downloadId: string) => {
    try {
      await api.cancelDownload(downloadId);
      await loadDownloads();
    } catch (error) {
      console.error('Error cancelling download:', error);
    }
  };

  const handleRetry = async (downloadId: string) => {
    try {
      await api.retryDownload(downloadId);
      await loadDownloads();
    } catch (error) {
      console.error('Error retrying download:', error);
    }
  };

  const handleClearHistory = async () => {
    showConfirm('Clear download history older than 7 days?', async () => {
      try {
        await api.clearDownloadHistory(7);
        await loadDownloads();
      } catch (error) {
        console.error('Error clearing history:', error);
      }
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending':
        return <Clock size={16} className="text-yellow-500" />;
      case 'downloading':
        return <Loader2 size={16} className="text-blue-500 animate-spin" />;
      case 'completed':
        return <CheckCircle size={16} className="text-green-500" />;
      case 'failed':
        return <XCircle size={16} className="text-red-500" />;
      case 'cancelled':
        return <XCircle size={16} className="text-muted-foreground" />;
      default:
        return <Clock size={16} className="text-muted-foreground" />;
    }
  };


  const activeDownloads = downloads.active.filter(
    (d) => d.status === 'pending' || d.status === 'downloading'
  );
  const recentCompleted = downloads.history
    .filter((d) => d.status === 'completed' || d.status === 'failed' || d.status === 'cancelled')
    .slice(0, 10);

  const hasActiveDownloads = activeDownloads.length > 0;
  const hasHistory = recentCompleted.length > 0;
  const isEmpty = !hasActiveDownloads && !hasHistory;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col p-0 overflow-x-hidden" style={{ maxWidth: 'min(95vw, 42rem)', width: 'min(95vw, 42rem)' }}>
        <DialogHeader className="p-6 border-b border-border flex-shrink-0 overflow-x-hidden max-w-full">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Download size={24} className="text-primary" />
              <div>
                <DialogTitle>Downloads</DialogTitle>
                <DialogDescription>
                  <span className={cn("hidden", hasActiveDownloads && "block")}>
                    {activeDownloads.length} active download{activeDownloads.length > 1 ? 's' : ''}
                  </span>
                  <span className={cn("hidden", !hasActiveDownloads && "block")}>
                    No active downloads
                  </span>
                </DialogDescription>
              </div>
            </div>
          </div>
        </DialogHeader>

        <ScrollArea className="flex-1 min-h-0 overflow-x-hidden">
          <div className="p-6 overflow-x-hidden max-w-full" style={{ width: '100%', maxWidth: '100%' }}>
            <div className={cn("hidden", loading && "block flex justify-center items-center py-12")}>
              <Loader2 size={32} className="animate-spin text-primary" />
            </div>
            <div className={cn("hidden", !loading && "block space-y-6 overflow-x-hidden max-w-full")} style={{ width: '100%', maxWidth: '100%' }}>
              <div className={cn("hidden", hasActiveDownloads && "block overflow-x-hidden max-w-full")} style={{ width: '100%', maxWidth: '100%' }}>
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                  Active Downloads
                </h3>
                <div className="space-y-3 overflow-x-hidden max-w-full" style={{ width: '100%', maxWidth: '100%' }}>
                  {activeDownloads.map((download) => {
                    const progress = download.progress ?? 0;
                    const bytesDownloaded = download.bytes_downloaded ?? 0;
                    const totalBytes = download.total_bytes ?? 0;
                    const speedMbps = download.speed_mbps ?? 0;
                    const etaSeconds = download.eta_seconds ?? null;
                    
                    // Debug logging for individual download
                    if (download.status === 'downloading') {
                      console.log(`[DownloadManager] Rendering download ${download.id}:`, {
                        progress,
                        bytesDownloaded,
                        totalBytes,
                        speedMbps,
                        etaSeconds,
                        rawData: download
                      });
                    }
                    
                    return (
                      <Card key={download.id} className="p-4 overflow-x-hidden max-w-full" style={{ width: '100%', maxWidth: '100%' }}>
                        <CardContent className="p-0 space-y-2 overflow-x-hidden max-w-full" style={{ width: '100%', maxWidth: '100%' }}>
                          <div className="flex items-start justify-between min-w-0 max-w-full overflow-x-hidden">
                            <div className="flex-1 min-w-0 overflow-x-hidden" style={{ minWidth: 0, maxWidth: '100%' }}>
                              <div className="flex items-center gap-2 min-w-0 overflow-x-hidden">
                                {getStatusIcon(download.status)}
                                <span className="font-medium truncate min-w-0" style={{ minWidth: 0 }}>{download.filename}</span>
                              </div>
                              <p className="text-xs text-muted-foreground truncate mt-0.5 min-w-0" style={{ minWidth: 0 }}>
                                {download.repo_id}
                              </p>
                            </div>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleCancel(download.id)}
                              className="h-6 w-6 flex-shrink-0"
                              title="Cancel download"
                            >
                              <X size={16} />
                            </Button>
                          </div>

                          <Progress value={progress} className="h-2 w-full" />

                          <div className="flex items-center justify-between text-xs text-muted-foreground min-w-0 max-w-full overflow-x-hidden flex-wrap gap-2">
                            <span className="truncate min-w-0">
                              {formatBytes(bytesDownloaded)} / {formatBytes(totalBytes)} ({progress.toFixed(1)}%)
                            </span>
                            <div className="flex items-center gap-3 flex-shrink-0">
                              <span className="whitespace-nowrap">{speedMbps > 0 ? `${speedMbps.toFixed(1)} MB/s` : '0.0 MB/s'}</span>
                              <span className="whitespace-nowrap">ETA: {etaSeconds !== null && etaSeconds !== undefined ? formatTime(etaSeconds) : '--'}</span>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </div>

              <div className={cn("hidden", isEmpty && "block text-center py-12 text-muted-foreground")}>
                <Download size={48} className="mx-auto mb-3 opacity-20" />
                <p className="text-lg font-medium">No downloads yet</p>
                <p className="text-sm">Downloads will appear here when you start downloading models</p>
              </div>

              <div className={cn("hidden", hasHistory && "block overflow-x-hidden max-w-full")} style={{ width: '100%', maxWidth: '100%' }}>
                <Accordion type="single" collapsible value={showHistory ? 'history' : undefined}>
                  <AccordionItem value="history">
                    <AccordionTrigger
                      onClick={() => setShowHistory(!showHistory)}
                      className="text-sm font-semibold text-muted-foreground uppercase tracking-wide"
                    >
                      Download History ({recentCompleted.length})
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-2 mt-3 overflow-x-hidden max-w-full" style={{ width: '100%', maxWidth: '100%' }}>
                        {recentCompleted.map((download) => (
                          <Card key={download.id} className="p-3 overflow-x-hidden max-w-full" style={{ width: '100%', maxWidth: '100%' }}>
                            <CardContent className="p-0 overflow-x-hidden max-w-full" style={{ width: '100%', maxWidth: '100%' }}>
                              <div className="flex items-center justify-between min-w-0 max-w-full overflow-x-hidden">
                                <div className="flex items-center gap-2 flex-1 min-w-0 overflow-x-hidden" style={{ minWidth: 0 }}>
                                  {getStatusIcon(download.status)}
                                  <span className="font-medium truncate text-sm min-w-0" style={{ minWidth: 0 }}>{download.filename}</span>
                                </div>
                                <div className="flex items-center gap-2 flex-shrink-0">
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => handleRetry(download.id)}
                                    className={cn("hidden h-6 w-6", download.status === 'failed' && "flex")}
                                    title="Retry download"
                                  >
                                    <RefreshCw size={14} />
                                  </Button>
                                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                                    {formatDate(download.completed_at)}
                                  </span>
                                </div>
                              </div>
                              <p className={cn("hidden text-xs text-destructive mt-1 truncate min-w-0", download.error && "block")} style={{ minWidth: 0 }} title={download.error}>
                                Error: {download.error}
                              </p>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
              </div>
            </div>
          </div>
        </ScrollArea>

        <div className="p-4 border-t border-border bg-muted/50 flex-shrink-0">
          <div className="flex items-center justify-between">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClearHistory}
              className="flex items-center gap-2 text-destructive hover:text-destructive"
            >
              <Trash2 size={14} />
              Clear History
            </Button>
            <Button onClick={onClose} variant="outline" size="sm">
              Close
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function DownloadBadge({ onClick }: { onClick: () => void }) {
  const [activeCount, setActiveCount] = useState(0);

  const updateCount = async () => {
    try {
      const data = (await api.listDownloads()) as DownloadsResponse;
      const active = data.active.filter(
        (d) => d.status === 'pending' || d.status === 'downloading'
      );
      setActiveCount(active.length);
    } catch {
      // Ignore errors
    }
  };

  // Update count from WebSocket events
  useWebSocketEvent('download_progress', updateCount);
  useWebSocketEvent('download_completed', updateCount);

  useEffect(() => {
    // Initial check only - then rely on WebSocket events
    updateCount();
  }, []);

  return (
    <Button variant="ghost" size="icon" onClick={onClick} className="relative" title="Downloads">
      <Download size={20} className={cn(activeCount > 0 ? 'text-primary' : 'text-muted-foreground')} />
      <Badge
        variant="destructive"
        className={cn(
          "hidden absolute -top-1 -right-1 h-5 w-5 p-0 flex items-center justify-center text-xs animate-pulse",
          activeCount > 0 && "flex"
        )}
      >
        {activeCount}
      </Badge>
    </Button>
  );
}
