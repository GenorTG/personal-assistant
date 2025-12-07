"use client";

import { useState, useEffect, useCallback } from "react";
import {
  X,
  Download,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  Trash2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { api } from "@/lib/api";
import { useToast } from "@/contexts/ToastContext";
import { formatBytes, formatTime, formatDate } from "@/lib/utils";

interface DownloadItem {
  id: string;
  repo_id: string;
  filename: string;
  status: "pending" | "downloading" | "completed" | "failed" | "cancelled";
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

  const loadDownloads = useCallback(async () => {
    try {
      const data = (await api.listDownloads()) as DownloadsResponse;
      setDownloads(data);

      // Check if any downloads just completed
      const justCompleted = data.active.some((d) => d.status === "completed");
      if (justCompleted && onDownloadComplete) {
        onDownloadComplete();
      }
    } catch (error) {
      console.error("Error loading downloads:", error);
    } finally {
      setLoading(false);
    }
  }, [onDownloadComplete]);

  useEffect(() => {
    if (isOpen) {
      loadDownloads();

      // Poll for updates every 1 second while open
      const interval = setInterval(loadDownloads, 1000);
      return () => clearInterval(interval);
    }
  }, [isOpen, loadDownloads]);

  const handleCancel = async (downloadId: string) => {
    try {
      await api.cancelDownload(downloadId);
      await loadDownloads();
    } catch (error) {
      console.error("Error cancelling download:", error);
    }
  };

  const handleRetry = async (downloadId: string) => {
    try {
      await api.retryDownload(downloadId);
      await loadDownloads();
    } catch (error) {
      console.error("Error retrying download:", error);
    }
  };

  const handleClearHistory = async () => {
    showConfirm("Clear download history older than 7 days?", async () => {
      try {
        await api.clearDownloadHistory(7);
        await loadDownloads();
      } catch (error) {
        console.error("Error clearing history:", error);
      }
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "pending":
        return <Clock size={16} className="text-yellow-500" />;
      case "downloading":
        return <Loader2 size={16} className="text-blue-500 animate-spin" />;
      case "completed":
        return <CheckCircle size={16} className="text-green-500" />;
      case "failed":
        return <XCircle size={16} className="text-red-500" />;
      case "cancelled":
        return <XCircle size={16} className="text-gray-400" />;
      default:
        return <Clock size={16} className="text-gray-400" />;
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case "pending":
        return "bg-yellow-50 border-yellow-200";
      case "downloading":
        return "bg-blue-50 border-blue-200";
      case "completed":
        return "bg-green-50 border-green-200";
      case "failed":
        return "bg-red-50 border-red-200";
      case "cancelled":
        return "bg-gray-50 border-gray-200";
      default:
        return "bg-gray-50 border-gray-200";
    }
  };

  if (!isOpen) return null;

  const activeDownloads = downloads.active.filter(
    (d) => d.status === "pending" || d.status === "downloading"
  );
  const recentCompleted = downloads.history
    .filter(
      (d) =>
        d.status === "completed" ||
        d.status === "failed" ||
        d.status === "cancelled"
    )
    .slice(0, 10);

  // Track mousedown to prevent closing when dragging text selection outside modal
  const [mouseDownInside, setMouseDownInside] = useState(false);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onMouseDown={(e) => {
        // Track if mousedown was on backdrop (outside modal)
        if (e.target === e.currentTarget) {
          setMouseDownInside(false);
        }
      }}
      onMouseUp={(e) => {
        // Only close if both mousedown and mouseup were on backdrop
        if (e.target === e.currentTarget && !mouseDownInside) {
          onClose();
        }
        setMouseDownInside(false);
      }}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        onMouseDown={(e) => {
          // Track that mousedown was inside modal
          setMouseDownInside(true);
          e.stopPropagation();
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-6 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <Download size={24} className="text-primary-600" />
            <div>
              <h2 className="text-xl font-bold text-gray-900">Downloads</h2>
              <p className="text-sm text-gray-500">
                {activeDownloads.length > 0
                  ? `${activeDownloads.length} active download${
                      activeDownloads.length > 1 ? "s" : ""
                    }`
                  : "No active downloads"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <X size={24} className="text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 min-h-0">
          {loading ? (
            <div className="flex justify-center items-center py-12">
              <Loader2 size={32} className="animate-spin text-primary-600" />
            </div>
          ) : (
            <>
              {/* Active Downloads */}
              {activeDownloads.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
                    Active Downloads
                  </h3>
                  <div className="space-y-3">
                    {activeDownloads.map((download) => (
                      <div
                        key={download.id}
                        className={`p-4 rounded-lg border ${getStatusColor(
                          download.status
                        )}`}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              {getStatusIcon(download.status)}
                              <span className="font-medium text-gray-900 truncate">
                                {download.filename}
                              </span>
                            </div>
                            <p className="text-xs text-gray-500 truncate mt-0.5">
                              {download.repo_id}
                            </p>
                          </div>
                          <button
                            onClick={() => handleCancel(download.id)}
                            className="p-1 rounded hover:bg-white/50 text-gray-500 hover:text-red-600"
                            title="Cancel download"
                          >
                            <X size={16} />
                          </button>
                        </div>

                        {/* Progress Bar */}
                        <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                          <div
                            className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${download.progress}%` }}
                          />
                        </div>

                        {/* Stats */}
                        <div className="flex items-center justify-between text-xs text-gray-600">
                          <span>
                            {formatBytes(download.bytes_downloaded)} /{" "}
                            {formatBytes(download.total_bytes)} (
                            {download.progress.toFixed(1)}%)
                          </span>
                          <div className="flex items-center gap-3">
                            <span>{download.speed_mbps.toFixed(1)} MB/s</span>
                            <span>ETA: {formatTime(download.eta_seconds)}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty State */}
              {activeDownloads.length === 0 && recentCompleted.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                  <Download size={48} className="mx-auto mb-3 opacity-20" />
                  <p className="text-lg font-medium">No downloads yet</p>
                  <p className="text-sm">
                    Downloads will appear here when you start downloading models
                  </p>
                </div>
              )}

              {/* History Section */}
              {recentCompleted.length > 0 && (
                <div>
                  <button
                    onClick={() => setShowHistory(!showHistory)}
                    className="flex items-center justify-between w-full text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3 hover:text-gray-900"
                  >
                    <span>Download History ({recentCompleted.length})</span>
                    {showHistory ? (
                      <ChevronUp size={16} />
                    ) : (
                      <ChevronDown size={16} />
                    )}
                  </button>

                  {showHistory && (
                    <div className="space-y-2">
                      {recentCompleted.map((download) => (
                        <div
                          key={download.id}
                          className={`p-3 rounded-lg border ${getStatusColor(
                            download.status
                          )}`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              {getStatusIcon(download.status)}
                              <span className="font-medium text-gray-900 truncate text-sm">
                                {download.filename}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              {download.status === "failed" && (
                                <button
                                  onClick={() => handleRetry(download.id)}
                                  className="p-1 rounded hover:bg-white/50 text-gray-500 hover:text-blue-600"
                                  title="Retry download"
                                >
                                  <RefreshCw size={14} />
                                </button>
                              )}
                              <span className="text-xs text-gray-500">
                                {formatDate(download.completed_at)}
                              </span>
                            </div>
                          </div>
                          {download.error && (
                            <p
                              className="text-xs text-red-600 mt-1 truncate"
                              title={download.error}
                            >
                              Error: {download.error}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 bg-gray-50 rounded-b-2xl flex-shrink-0">
          <div className="flex items-center justify-between">
            <button
              onClick={handleClearHistory}
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-red-600 transition-colors"
            >
              <Trash2 size={14} />
              Clear History
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm font-medium transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Mini badge for showing in header
export function DownloadBadge({ onClick }: { onClick: () => void }) {
  const [activeCount, setActiveCount] = useState(0);

  useEffect(() => {
    const checkDownloads = async () => {
      try {
        const data = (await api.listDownloads()) as DownloadsResponse;
        const active = data.active.filter(
          (d) => d.status === "pending" || d.status === "downloading"
        );
        setActiveCount(active.length);
      } catch {
        // Ignore errors
      }
    };

    checkDownloads();
    const interval = setInterval(checkDownloads, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <button
      onClick={onClick}
      className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors"
      title="Downloads"
    >
      <Download
        size={20}
        className={activeCount > 0 ? "text-blue-600" : "text-gray-500"}
      />
      {activeCount > 0 && (
        <span className="absolute -top-1 -right-1 w-5 h-5 bg-blue-600 text-white text-xs rounded-full flex items-center justify-center font-medium animate-pulse">
          {activeCount}
        </span>
      )}
    </button>
  );
}
