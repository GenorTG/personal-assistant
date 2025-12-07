import React, { useState } from 'react';
import { formatNumber, formatDateShort } from '@/lib/utils';
import { CheckCircle, Eye, Heart, Calendar, User, Cpu, Hash, Package, Edit3, Trash2, Loader2 } from 'lucide-react';

interface ModelSearchResultCardProps {
  model: any;
  onLoad?: (modelId: string) => void;
  onDownload?: (modelId: string) => void;
  onViewDetails?: (modelId: string) => void;
  onEditMetadata?: (model: any) => void;
  onDelete?: (modelId: string) => Promise<void>;
  isCurrent?: boolean;
}

export default function ModelSearchResultCard({ 
  model, 
  onLoad, 
  onDownload, 
  onViewDetails,
  onEditMetadata,
  onDelete,
  isCurrent
}: ModelSearchResultCardProps) {
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleAction = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onViewDetails) {
      onViewDetails(model.model_id);
    } else if (onDownload) {
      onDownload(model.model_id);
    } else if (onLoad && !isCurrent) {
      onLoad(model.model_id);
    }
  };
  
  const handleEditMetadata = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onEditMetadata) {
      onEditMetadata(model);
    }
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isCurrent) return; // Can't delete loaded model
    setConfirmDelete(true);
  };

  const handleConfirmDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onDelete) return;
    
    setDeleting(true);
    try {
      await onDelete(model.model_id);
    } catch (err) {
      console.error('Delete failed:', err);
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirmDelete(false);
  };

  const getButtonContent = () => {
    if (onViewDetails) {
      return (
        <>
          <Eye size={16} className="mr-2" />
          View Details
        </>
      );
    } else if (onDownload) {
      return 'Download';
    } else if (isCurrent) {
      return (
        <>
          <CheckCircle size={16} className="mr-2" /> Loaded
        </>
      );
    }
    return 'Load';
  };

  const buttonDisabled = isCurrent && !onDownload && !onViewDetails;
  

  return (
    <div className={`group relative bg-white rounded-xl border transition-all duration-200 hover:shadow-lg hover:border-primary-300 ${isCurrent ? 'border-green-500 ring-1 ring-green-500 bg-green-50/30' : 'border-gray-200'}`}>
      <div className="p-5">
        {/* Header */}
        <div className="flex justify-between items-start mb-3">
          <div className="flex-1 min-w-0 mr-4">
            <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
              <User size={12} />
              {model.repo_id ? (
                <a 
                  href={`https://huggingface.co/${model.repo_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="truncate hover:text-primary-600 hover:underline"
                  onClick={(e) => e.stopPropagation()}
                >
                  {model.author || model.repo_id.split('/')[0] || 'Unknown'}
                </a>
              ) : (
                <span className="truncate">{model.author || 'Unknown'}</span>
              )}
            </div>
            <h3 className="font-bold text-gray-900 truncate text-lg" title={model.repo_name || model.name}>
              {model.repo_name || model.name}
            </h3>
            {model.repo_id && (
              <p className="text-xs text-gray-400 truncate" title={model.model_id}>
                {model.model_id}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1">
            {isCurrent && (
              <span className="flex-shrink-0 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Active
              </span>
            )}
            {(model.discovered || model.has_metadata) && (
              <span className="flex-shrink-0 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" title="Metadata from HuggingFace">
                {model.huggingface_url ? 'Linked' : 'Scanned'}
              </span>
            )}
          </div>
        </div>

        {/* Stats */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500 mb-4">
          {/* Size */}
          {model.size && (
            <div className="flex items-center gap-1" title="File Size">
              <Package size={14} />
              <span className="font-medium text-gray-700">{model.size}</span>
            </div>
          )}
          {/* Architecture from discovered metadata */}
          {model.architecture && (
            <div className="flex items-center gap-1" title="Architecture">
              <Cpu size={14} />
              <span className="font-medium text-gray-700">{model.architecture}</span>
            </div>
          )}
          {/* Parameters from discovered metadata */}
          {model.parameters && (
            <div className="flex items-center gap-1" title="Parameters">
              <Hash size={14} />
              <span className="font-medium text-gray-700">{model.parameters}</span>
            </div>
          )}
          {/* Quantization from discovered metadata */}
          {model.quantization && (
            <div className="flex items-center gap-1" title="Quantization">
              <Package size={14} />
              <span className="font-medium text-gray-700">{model.quantization}</span>
            </div>
          )}
          {model.downloads !== undefined && model.downloads > 0 && (
            <div className="flex items-center gap-1" title="Downloads">
              <Heart size={14} />
              <span>{formatNumber(model.downloads)}</span>
            </div>
          )}
          {model.likes !== undefined && (
            <div className="flex items-center gap-1" title="Likes">
              <Heart size={14} />
              <span>{formatNumber(model.likes)}</span>
            </div>
          )}
          {model.last_modified && (
            <div className="flex items-center gap-1" title="Last Updated">
              <Calendar size={14} />
              <span>{formatDateShort(model.last_modified)}</span>
            </div>
          )}
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-1.5 mb-4 max-h-16 overflow-hidden">
          {model.pipeline_tag && (
            <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-primary-50 text-primary-700">
              {model.pipeline_tag}
            </span>
          )}
          {model.tags?.slice(0, 5).map((tag: string) => (
            <span key={tag} className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-gray-100 text-gray-600">
              {tag}
            </span>
          ))}
          {model.tags?.length > 5 && (
            <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-gray-50 text-gray-500">
              +{model.tags.length - 5}
            </span>
          )}
        </div>

        {/* Action Buttons */}
        {confirmDelete ? (
          /* Delete Confirmation */
          <div className="flex gap-2 items-center bg-red-50 border border-red-200 rounded-lg p-2">
            <span className="text-sm text-red-700 flex-1">Delete this model?</span>
            <button
              onClick={handleCancelDelete}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirmDelete}
              disabled={deleting}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors flex items-center gap-1"
            >
              {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              {deleting ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        ) : (
          <div className="flex gap-2">
            {/* Edit Metadata Button - only for installed models */}
            {onEditMetadata && !onViewDetails && (
              <button
                onClick={handleEditMetadata}
                className="flex items-center justify-center px-3 py-2 rounded-lg text-sm font-medium transition-colors bg-white border border-gray-300 text-gray-600 hover:bg-gray-50 hover:text-primary-600 hover:border-primary-300"
                title="Edit metadata"
              >
                <Edit3 size={16} />
              </button>
            )}
            
            {/* Delete Button - only for installed models that are not loaded */}
            {onDelete && !onViewDetails && !isCurrent && (
              <button
                onClick={handleDeleteClick}
                className="flex items-center justify-center px-3 py-2 rounded-lg text-sm font-medium transition-colors bg-white border border-gray-300 text-gray-600 hover:bg-red-50 hover:text-red-600 hover:border-red-300"
                title="Delete model"
              >
                <Trash2 size={16} />
              </button>
            )}
            
            {/* Main Action Button */}
            <button
              onClick={handleAction}
              disabled={buttonDisabled}
              className={`flex-1 flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                onViewDetails
                  ? 'bg-primary-600 text-white hover:bg-primary-700 shadow-sm hover:shadow'
                  : onDownload
                  ? 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 hover:text-primary-600 hover:border-primary-300'
                  : isCurrent
                  ? 'bg-green-100 text-green-700 cursor-default'
                  : 'bg-primary-600 text-white hover:bg-primary-700 shadow-sm hover:shadow'
              }`}
            >
              {getButtonContent()}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
