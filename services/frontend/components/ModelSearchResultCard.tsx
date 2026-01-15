'use client';

import React, { useState } from 'react';
import { formatNumber, formatDateShort } from '@/lib/utils';
import {
  CheckCircle,
  Eye,
  Heart,
  Calendar,
  User,
  Cpu,
  Hash,
  Package,
  Edit3,
  Trash2,
  Loader2,
  Wrench,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

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
  isCurrent,
}: ModelSearchResultCardProps) {
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Early return if model is null
  if (!model) {
    return null;
  }

  const modelId = model.model_id || '';
  const repoId = model.repo_id || '';
  const author = model.author || (repoId ? repoId.split('/')[0] : '') || 'Unknown';
  const repoName = model.repo_name || model.name || 'Unknown';

  const handleAction = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!modelId) return;
    if (onViewDetails) {
      onViewDetails(modelId);
    } else if (onDownload) {
      onDownload(modelId);
    } else if (onLoad && !isCurrent) {
      onLoad(modelId);
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
    if (isCurrent) return;
    setConfirmDelete(true);
  };

  const handleConfirmDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onDelete || !modelId) return;

    setDeleting(true);
    try {
      await onDelete(modelId);
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

  const buttonDisabled = isCurrent && !onDownload && !onViewDetails;
  const showEditButton = onEditMetadata && !onViewDetails;
  const showDeleteButton = onDelete && !onViewDetails && !isCurrent;

  return (
    <Card
      className={cn(
        'group relative transition-all duration-200 hover:shadow-lg w-full min-w-0 max-w-full overflow-hidden',
        isCurrent && 'border-green-500 ring-1 ring-green-500 bg-green-50/30'
      )}
      style={{ maxWidth: '100%', width: '100%' }}
    >
      <CardContent className="p-4 sm:p-5 min-w-0 max-w-full overflow-x-hidden" style={{ maxWidth: '100%' }}>
        <div className="flex justify-between items-start mb-3 min-w-0 max-w-full overflow-x-hidden">
          <div className="flex-1 min-w-0 mr-4 overflow-x-hidden" style={{ minWidth: 0, maxWidth: '100%' }}>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
              <User size={12} />
              <div className={cn("hidden", repoId && "block")}>
                <a
                  href={`https://huggingface.co/${repoId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="truncate hover:text-primary hover:underline"
                  onClick={(e) => e.stopPropagation()}
                >
                  {author}
                </a>
              </div>
              <span className={cn("hidden", !repoId && "block truncate")}>
                {author}
              </span>
            </div>
            <h3 className="font-bold truncate text-base sm:text-lg" title={repoName}>
              {repoName}
            </h3>
            <p className={cn("hidden", modelId && "block text-xs text-muted-foreground truncate")} title={modelId}>
              {modelId}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1 flex-shrink-0">
            <Badge variant={isCurrent ? "default" : "secondary"} className={cn("hidden", isCurrent && "block bg-green-100 text-green-800")}>
              Active
            </Badge>
            <Badge
              variant="secondary"
              className={cn("hidden", (model.discovered || model.has_metadata) && "block")}
              title="Metadata from HuggingFace"
            >
              {model.huggingface_url ? 'Linked' : 'Scanned'}
            </Badge>
            {model.supports_tool_calling !== undefined && (
              <Badge
                variant={model.supports_tool_calling === true ? "default" : "outline"}
                className={cn(
                  "flex items-center gap-1 flex-shrink-0",
                  model.supports_tool_calling === true && "bg-blue-100 text-blue-800 border-blue-300"
                )}
                title={model.supports_tool_calling === true ? "Supports tool calling (function calling)" : "Does not support tool calling"}
              >
                <Wrench size={12} className="flex-shrink-0" />
                <span className="whitespace-nowrap">{model.supports_tool_calling === true ? "Tools" : "No Tools"}</span>
              </Badge>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs text-muted-foreground mb-4 min-w-0 max-w-full overflow-x-hidden">
          <div className={cn("hidden", model.size && "flex items-center gap-1 min-w-0 max-w-full")} title="File Size">
            <Package size={14} className="flex-shrink-0" />
            <span className="font-medium truncate max-w-full">{model.size}</span>
          </div>
          <div className={cn("hidden", model.architecture && "flex items-center gap-1 min-w-0 max-w-full")} title="Architecture">
            <Cpu size={14} className="flex-shrink-0" />
            <span className="font-medium truncate max-w-full">{model.architecture}</span>
          </div>
          <div className={cn("hidden", model.parameters && "flex items-center gap-1 min-w-0 max-w-full")} title="Parameters">
            <Hash size={14} className="flex-shrink-0" />
            <span className="font-medium truncate max-w-full">{model.parameters}</span>
          </div>
          <div className={cn("hidden", model.quantization && "flex items-center gap-1 min-w-0 max-w-full")} title="Quantization">
            <Package size={14} className="flex-shrink-0" />
            <span className="font-medium truncate max-w-full">{model.quantization}</span>
          </div>
          <div className={cn("hidden", model.downloads !== undefined && model.downloads !== null && model.downloads > 0 && "flex items-center gap-1 min-w-0 max-w-full")} title="Downloads">
            <Heart size={14} className="flex-shrink-0" />
            <span className="truncate max-w-full">{formatNumber(model.downloads)}</span>
          </div>
          <div className={cn("hidden", model.likes !== undefined && model.likes !== null && "flex items-center gap-1 min-w-0 max-w-full")} title="Likes">
            <Heart size={14} className="flex-shrink-0" />
            <span className="truncate max-w-full">{formatNumber(model.likes)}</span>
          </div>
          <div className={cn("hidden", model.last_modified && "flex items-center gap-1 min-w-0 max-w-full")} title="Last Updated">
            <Calendar size={14} className="flex-shrink-0" />
            <span className="truncate max-w-full">{formatDateShort(model.last_modified)}</span>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 mb-4 max-h-16 overflow-hidden overflow-x-hidden min-w-0 max-w-full">
          <Badge variant="outline" className={cn("hidden", model.pipeline_tag && "block max-w-[200px] min-w-0")} title={model.pipeline_tag}>
            <span className="truncate block">{model.pipeline_tag}</span>
          </Badge>
          {model.tags?.slice(0, 5).map((tag: string) => (
            <Badge key={tag} variant="secondary" className="max-w-[200px] min-w-0" title={tag}>
              <span className="truncate block">{tag}</span>
            </Badge>
          ))}
          <Badge variant="outline" className={cn("hidden", model.tags && model.tags.length > 5 && "block flex-shrink-0")}>
            +{model.tags ? model.tags.length - 5 : 0}
          </Badge>
        </div>

        <div className={cn("hidden", confirmDelete && "block")}>
          <div className="flex gap-2 items-center bg-destructive/10 border border-destructive/20 rounded p-2">
            <span className="text-sm text-destructive flex-1">Delete this model?</span>
            <Button onClick={handleCancelDelete} variant="outline" size="sm">
              Cancel
            </Button>
            <Button onClick={handleConfirmDelete} disabled={deleting} variant="destructive" size="sm" className="flex items-center gap-1">
              {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              {deleting ? 'Deleting...' : 'Delete'}
            </Button>
          </div>
        </div>
        <div className={cn("hidden", !confirmDelete && "block flex gap-2 min-w-0 max-w-full overflow-x-hidden")}>
          <Button
            variant="outline"
            size="icon"
            onClick={handleEditMetadata}
            className={cn("hidden", showEditButton && "flex flex-shrink-0")}
            title="Edit metadata"
          >
            <Edit3 size={16} />
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={handleDeleteClick}
            className={cn("hidden", showDeleteButton && "flex flex-shrink-0 hover:bg-destructive hover:text-destructive-foreground")}
            title="Delete model"
          >
            <Trash2 size={16} />
          </Button>
          <Button
            onClick={handleAction}
            disabled={buttonDisabled}
            variant={onViewDetails ? 'default' : onDownload ? 'outline' : isCurrent ? 'secondary' : 'default'}
            className="flex-1 flex items-center justify-center gap-2 min-w-0 overflow-x-hidden"
            style={{ minWidth: 0 }}
          >
            {onViewDetails && (
              <>
                <Eye size={16} />
                View Details
              </>
            )}
            {!onViewDetails && onDownload && 'Download'}
            {!onViewDetails && !onDownload && isCurrent && (
              <>
                <CheckCircle size={16} />
                Loaded
              </>
            )}
            {!onViewDetails && !onDownload && !isCurrent && 'Load'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
