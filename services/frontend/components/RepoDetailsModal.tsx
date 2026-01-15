"use client";

import { useState, useEffect, useCallback } from "react";
import {
  X,
  Download,
  Calendar,
  TrendingUp,
  HardDrive,
  User,
  ChevronDown,
  ExternalLink,
} from "lucide-react";
import { formatNumber, formatFileSize, formatDateShort } from "@/lib/utils";
import { api } from "@/lib/api";

interface RepoDetailsModalProps {
  modelId: string;
  onClose: () => void;
  onDownload: (filename: string) => void;
}

interface ModelFile {
  filename: string;
  rfilename?: string;
  size?: number;
  size_str?: string;
  size_info: string | null;
}

interface ModelDetails {
  name: string;
  full_name: string;
  author: string;
  description: string;
  downloads: number;
  last_modified: string | null;
  architecture: string;
  tags: string[];
}

export default function RepoDetailsModal({
  modelId,
  onClose,
  onDownload,
}: RepoDetailsModalProps) {
  const [details, setDetails] = useState<ModelDetails | null>(null);
  const [files, setFiles] = useState<ModelFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string>("");

  const loadModelData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [detailsData, filesData] = await Promise.all([
        api.getModelDetails(modelId),
        api.getModelFiles(modelId),
      ]);

      setDetails(detailsData);
      const fileList = Array.isArray(filesData)
        ? filesData
        : filesData.files || [];
      setFiles(fileList);

      // Auto-select first Q4_K_M or Q4_0 file, or first file
      const preferredFile =
        fileList.find(
          (f: ModelFile) =>
            f.filename.includes("Q4_K_M") || f.filename.includes("Q4_0")
        ) || fileList[0];
      if (preferredFile) {
        setSelectedFile(preferredFile.filename);
      }
    } catch (err: any) {
      console.error("Error loading model data:", err);
      setError(err.message || "Failed to load model information");
    } finally {
      setLoading(false);
    }
  }, [modelId]);

  useEffect(() => {
    loadModelData();

    // Close on Escape key
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [modelId, onClose, loadModelData]);

  const handleDownloadFile = () => {
    if (selectedFile) {
      onDownload(selectedFile);
    }
  };

  // Track mousedown to prevent closing when dragging text selection outside modal
  const [mouseDownInside, setMouseDownInside] = useState(false);

  const handleBackdropMouseDown = (e: React.MouseEvent) => {
    // Track if mousedown was on backdrop (outside modal)
    if (e.target === e.currentTarget) {
      setMouseDownInside(false);
    }
  };

  const handleBackdropMouseUp = (e: React.MouseEvent) => {
    // Only close if both mousedown and mouseup were on backdrop
    if (e.target === e.currentTarget && !mouseDownInside) {
      onClose();
    }
    setMouseDownInside(false);
  };

  const handleContentMouseDown = (e: React.MouseEvent) => {
    // Track that mousedown was inside modal
    setMouseDownInside(true);
    e.stopPropagation();
  };

  // Loading state
  if (loading) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        onMouseDown={handleBackdropMouseDown}
        onMouseUp={handleBackdropMouseUp}
      >
        <div
          className="bg-white rounded p-8 max-w-2xl w-full mx-4 shadow-2xl overflow-x-hidden"
          style={{ maxWidth: 'min(95vw, 42rem)', width: 'min(95vw, 42rem)' }}
          onMouseDown={handleContentMouseDown}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-bold text-gray-900">
              Loading Model Details...
            </h2>
            <button
              onClick={onClose}
              className="p-2 rounded hover:bg-gray-100 transition-colors"
              title="Close (Esc)"
            >
              <X size={24} className="text-gray-500" />
            </button>
          </div>
          <div className="flex justify-center items-center py-12">
            <div className="animate-spin rounded h-12 w-12 border-b-2 border-primary-600"></div>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !details) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        onMouseDown={handleBackdropMouseDown}
        onMouseUp={handleBackdropMouseUp}
      >
      <div
        className="bg-white rounded p-8 max-w-2xl w-full mx-4 shadow-2xl overflow-x-hidden"
        style={{ maxWidth: 'min(95vw, 42rem)', width: 'min(95vw, 42rem)' }}
        onMouseDown={handleContentMouseDown}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-6">
            <h2 className="text-2xl font-bold text-red-600">
              Error Loading Model
            </h2>
            <button
              onClick={onClose}
              className="p-2 rounded hover:bg-gray-100 transition-colors"
              title="Close (Esc)"
            >
              <X size={24} className="text-gray-500" />
            </button>
          </div>
          <p className="text-gray-600 mb-6">
            {error || "Failed to load model details"}
          </p>
          <div className="flex justify-end">
            <button
              onClick={onClose}
              className="px-6 py-2 bg-gray-100 hover:bg-gray-200 rounded font-medium transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  const selectedFileInfo = files.find((f) => f.filename === selectedFile);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onMouseDown={handleBackdropMouseDown}
      onMouseUp={handleBackdropMouseUp}
    >
      <div
        className="bg-white rounded shadow-2xl max-w-3xl w-full max-h-[85vh] flex flex-col overflow-x-hidden"
        style={{ maxWidth: 'min(95vw, 48rem)', width: 'min(95vw, 48rem)' }}
        onMouseDown={handleContentMouseDown}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-6 border-b border-gray-200 flex-shrink-0">
          <div className="flex justify-between items-start">
            <div className="flex-1 pr-4">
              <h2 className="text-2xl font-bold text-gray-900 mb-1">
                {details.name}
              </h2>
              <div className="flex items-center gap-3 text-sm text-gray-600">
                <div className="flex items-center gap-1">
                  <User size={14} />
                  <span>{details.author}</span>
                </div>
                {details.architecture && details.architecture !== "Unknown" && (
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-primary-100 text-primary-800">
                    {details.architecture}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded hover:bg-gray-100 transition-colors flex-shrink-0"
              title="Close (Esc)"
            >
              <X size={24} className="text-gray-500" />
            </button>
          </div>

          {/* Stats */}
          <div className="flex gap-4 mt-4 text-sm text-gray-600">
            <div className="flex items-center gap-1">
              <TrendingUp size={14} />
              <span className="font-medium">
                {formatNumber(details.downloads)}
              </span>
              <span>downloads</span>
            </div>
            <div className="flex items-center gap-1">
              <Calendar size={14} />
              <span>Updated {formatDateShort(details.last_modified)}</span>
            </div>
            <div className="flex items-center gap-1">
              <HardDrive size={14} />
              <span>{files.length} files</span>
            </div>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 min-h-0">
          {/* Description */}
          {details.description && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">
                Description
              </h3>
              <div className="bg-gray-50 rounded p-4 max-h-48 overflow-y-auto">
                <p className="text-gray-700 text-sm whitespace-pre-wrap leading-relaxed">
                  {details.description}
                </p>
              </div>
            </div>
          )}

          {/* Tags */}
          {details.tags && details.tags.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">
                Tags
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {details.tags.slice(0, 12).map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-1 rounded text-xs bg-gray-100 text-gray-600"
                  >
                    {tag}
                  </span>
                ))}
                {details.tags.length > 12 && (
                  <span className="px-2 py-1 rounded text-xs bg-gray-50 text-gray-400">
                    +{details.tags.length - 12} more
                  </span>
                )}
              </div>
            </div>
          )}

          {/* File Selection */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">
              Select Quantization ({files.length} available)
            </h3>

            {files.length > 0 ? (
              <div className="relative">
                <select
                  value={selectedFile}
                  onChange={(e) => setSelectedFile(e.target.value)}
                  className="w-full p-3 pr-10 border border-gray-300 rounded bg-white text-gray-900 font-medium appearance-none cursor-pointer hover:border-primary-400 focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all"
                >
                  {files.map((file) => {
                    const sizeDisplay =
                      file.size_str ||
                      (file.size && file.size > 0
                        ? formatFileSize(file.size)
                        : "");
                    const quantDisplay = file.size_info
                      ? ` - ${file.size_info}`
                      : "";
                    return (
                      <option key={file.filename} value={file.filename}>
                        {file.filename}
                        {sizeDisplay
                          ? ` (${sizeDisplay}${quantDisplay})`
                          : quantDisplay
                          ? ` (${quantDisplay.trim()})`
                          : ""}
                      </option>
                    );
                  })}
                </select>
                <ChevronDown
                  size={20}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
                />
              </div>
            ) : (
              <div className="text-center py-6 text-gray-500 bg-gray-50 rounded">
                <HardDrive size={32} className="mx-auto mb-2 opacity-30" />
                <p>No GGUF files found in this repository</p>
              </div>
            )}

            {selectedFileInfo && (
              <div className="mt-3 p-3 bg-primary-50 rounded border border-primary-100">
                <p
                  className="text-sm text-primary-800 font-medium truncate"
                  title={selectedFile}
                >
                  Selected: {selectedFile}
                </p>
                <div className="flex gap-4 mt-2 text-xs text-primary-600">
                  {selectedFileInfo.size_str ||
                  (selectedFileInfo.size && selectedFileInfo.size > 0
                    ? formatFileSize(selectedFileInfo.size)
                    : null) ? (
                    <span className="font-medium">
                      Size:{" "}
                      {selectedFileInfo.size_str ||
                        formatFileSize(selectedFileInfo.size || 0)}
                    </span>
                  ) : null}
                  {selectedFileInfo.size_info && (
                    <span>Quantization: {selectedFileInfo.size_info}</span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer with Actions */}
        <div className="p-6 border-t border-gray-200 bg-gray-50 rounded-b-2xl flex-shrink-0">
          <div className="flex items-center justify-between gap-4">
            <a
              href={`https://huggingface.co/${modelId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-primary-600 transition-colors"
            >
              <ExternalLink size={16} />
              View on HuggingFace
            </a>

            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="px-6 py-2.5 bg-white border border-gray-300 rounded font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDownloadFile}
                disabled={!selectedFile}
                className="flex items-center gap-2 px-6 py-2.5 bg-red-500 text-white rounded font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
              >
                <Download size={18} />
                Download Selected
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
