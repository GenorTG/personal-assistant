'use client';

import { useState, useEffect } from 'react';
import { X, Download, Calendar, TrendingUp, HardDrive, Tag, User, ChevronDown, ExternalLink } from 'lucide-react';

interface RepoDetailsModalProps {
  modelId: string;
  onClose: () => void;
  onDownload: (filename: string) => void;
}

interface ModelFile {
  filename: string;
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

export default function RepoDetailsModal({ modelId, onClose, onDownload }: RepoDetailsModalProps) {
  const [details, setDetails] = useState<ModelDetails | null>(null);
  const [files, setFiles] = useState<ModelFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string>('');

  useEffect(() => {
    loadModelData();
    
    // Close on Escape key
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [modelId]);

  const loadModelData = async () => {
    setLoading(true);
    setError(null);
    
    const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    
    try {
      const [detailsRes, filesRes] = await Promise.all([
        fetch(`${API_BASE}/api/models/${encodeURIComponent(modelId)}/details`),
        fetch(`${API_BASE}/api/models/${encodeURIComponent(modelId)}/files`)
      ]);

      if (!detailsRes.ok) {
        const errorData = await detailsRes.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to fetch model details: ${detailsRes.statusText}`);
      }
      if (!filesRes.ok) {
        const errorData = await filesRes.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to fetch model files: ${filesRes.statusText}`);
      }

      const detailsData = await detailsRes.json();
      const filesData = await filesRes.json();

      setDetails(detailsData);
      const fileList = Array.isArray(filesData) ? filesData : (filesData.files || []);
      setFiles(fileList);
      
      // Auto-select first Q4_K_M or Q4_0 file, or first file
      const preferredFile = fileList.find((f: ModelFile) => 
        f.filename.includes('Q4_K_M') || f.filename.includes('Q4_0')
      ) || fileList[0];
      if (preferredFile) {
        setSelectedFile(preferredFile.filename);
      }
    } catch (err: any) {
      console.error('Error loading model data:', err);
      setError(err.message || 'Failed to load model information');
    } finally {
      setLoading(false);
    }
  };

  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}k`;
    return num.toString();
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Unknown';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return 'Unknown';
    }
  };

  const handleDownloadFile = () => {
    if (selectedFile) {
      onDownload(selectedFile);
    }
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  // Loading state
  if (loading) {
    return (
      <div 
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        onClick={handleBackdropClick}
      >
        <div className="bg-white rounded-2xl p-8 max-w-2xl w-full mx-4 shadow-2xl">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-bold text-gray-900">Loading Model Details...</h2>
            <button 
              onClick={onClose} 
              className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
              title="Close (Esc)"
            >
              <X size={24} className="text-gray-500" />
            </button>
          </div>
          <div className="flex justify-center items-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
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
        onClick={handleBackdropClick}
      >
        <div className="bg-white rounded-2xl p-8 max-w-2xl w-full mx-4 shadow-2xl">
          <div className="flex justify-between items-start mb-6">
            <h2 className="text-2xl font-bold text-red-600">Error Loading Model</h2>
            <button 
              onClick={onClose} 
              className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
              title="Close (Esc)"
            >
              <X size={24} className="text-gray-500" />
            </button>
          </div>
          <p className="text-gray-600 mb-6">{error || 'Failed to load model details'}</p>
          <div className="flex justify-end">
            <button 
              onClick={onClose} 
              className="px-6 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  const selectedFileInfo = files.find(f => f.filename === selectedFile);

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={handleBackdropClick}
    >
      <div 
        className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-6 border-b border-gray-200 flex-shrink-0">
          <div className="flex justify-between items-start">
            <div className="flex-1 pr-4">
              <h2 className="text-2xl font-bold text-gray-900 mb-1">{details.name}</h2>
              <div className="flex items-center gap-3 text-sm text-gray-600">
                <div className="flex items-center gap-1">
                  <User size={14} />
                  <span>{details.author}</span>
                </div>
                {details.architecture && details.architecture !== 'Unknown' && (
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-primary-100 text-primary-800">
                    {details.architecture}
                  </span>
                )}
              </div>
            </div>
            <button 
              onClick={onClose} 
              className="p-2 rounded-lg hover:bg-gray-100 transition-colors flex-shrink-0"
              title="Close (Esc)"
            >
              <X size={24} className="text-gray-500" />
            </button>
          </div>
          
          {/* Stats */}
          <div className="flex gap-4 mt-4 text-sm text-gray-600">
            <div className="flex items-center gap-1">
              <TrendingUp size={14} />
              <span className="font-medium">{formatNumber(details.downloads)}</span>
              <span>downloads</span>
            </div>
            <div className="flex items-center gap-1">
              <Calendar size={14} />
              <span>Updated {formatDate(details.last_modified)}</span>
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
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Description</h3>
              <div className="bg-gray-50 rounded-lg p-4 max-h-48 overflow-y-auto">
                <p className="text-gray-700 text-sm whitespace-pre-wrap leading-relaxed">
                  {details.description}
                </p>
              </div>
            </div>
          )}

          {/* Tags */}
          {details.tags && details.tags.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Tags</h3>
              <div className="flex flex-wrap gap-1.5">
                {details.tags.slice(0, 12).map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-1 rounded-md text-xs bg-gray-100 text-gray-600"
                  >
                    {tag}
                  </span>
                ))}
                {details.tags.length > 12 && (
                  <span className="px-2 py-1 rounded-md text-xs bg-gray-50 text-gray-400">
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
                  className="w-full p-3 pr-10 border border-gray-300 rounded-lg bg-white text-gray-900 font-medium appearance-none cursor-pointer hover:border-primary-400 focus:border-primary-500 focus:ring-2 focus:ring-primary-200 transition-all"
                >
                  {files.map((file) => (
                    <option key={file.filename} value={file.filename}>
                      {file.filename} {file.size_info ? `(${file.size_info})` : ''}
                    </option>
                  ))}
                </select>
                <ChevronDown 
                  size={20} 
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" 
                />
              </div>
            ) : (
              <div className="text-center py-6 text-gray-500 bg-gray-50 rounded-lg">
                <HardDrive size={32} className="mx-auto mb-2 opacity-30" />
                <p>No GGUF files found in this repository</p>
              </div>
            )}

            {selectedFileInfo && (
              <div className="mt-3 p-3 bg-primary-50 rounded-lg border border-primary-100">
                <p className="text-sm text-primary-800 font-medium truncate" title={selectedFile}>
                  Selected: {selectedFile}
                </p>
                {selectedFileInfo.size_info && (
                  <p className="text-xs text-primary-600 mt-1">
                    Quantization: {selectedFileInfo.size_info}
                  </p>
                )}
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
                className="px-6 py-2.5 bg-white border border-gray-300 rounded-lg font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDownloadFile}
                disabled={!selectedFile}
                className="flex items-center gap-2 px-6 py-2.5 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
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
