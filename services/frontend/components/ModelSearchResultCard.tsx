import React from 'react';
import { CheckCircle, Download, Heart, Calendar, User, HardDrive } from 'lucide-react';
import { calculateMemory, extractParams } from '@/lib/memory-calculator';

interface ModelSearchResultCardProps {
  model: any;
  onLoad?: (modelId: string) => void;
  onDownload?: (modelId: string) => void;
  isCurrent?: boolean;
  availableVram?: number;
  targetContext?: number;
}

export default function ModelSearchResultCard({ 
  model, 
  onLoad, 
  onDownload, 
  isCurrent,
  availableVram = 0,
  targetContext = 4096
}: ModelSearchResultCardProps) {
  const handleAction = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDownload) {
      onDownload(model.model_id);
    } else if (onLoad && !isCurrent) {
      onLoad(model.model_id);
    }
  };

  const buttonLabel = onDownload ? (
    <>
      <Download size={16} className="mr-2" />
      Download
    </>
  ) : (
    isCurrent ? (
      <>
        <CheckCircle size={16} className="mr-2" /> Loaded
      </>
    ) : (
      'Load'
    )
  );

  const buttonDisabled = isCurrent && !onDownload;
  
  // Format numbers
  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}k`;
    return num;
  };

  // Format date
  const formatDate = (dateString: string) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleDateString();
  };

  // Calculate VRAM fit
  const params = React.useMemo(() => {
    return extractParams(model.name, model.tags);
  }, [model]);

  const memoryInfo = React.useMemo(() => {
    if (!params) return null;
    // Default to Q4_K_M for estimation if not specified in filename
    const quant = model.name.match(/Q\d+_K?[MS]?|Q\d+_\d+|F16/i)?.[0] || "Q4_K_M";
    return calculateMemory(params, quant, targetContext, availableVram);
  }, [params, model.name, targetContext, availableVram]);

  return (
    <div className={`group relative bg-white rounded-xl border transition-all duration-200 hover:shadow-lg hover:border-primary-300 ${isCurrent ? 'border-green-500 ring-1 ring-green-500 bg-green-50/30' : 'border-gray-200'}`}>
      <div className="p-5">
        {/* Header */}
        <div className="flex justify-between items-start mb-3">
          <div className="flex-1 min-w-0 mr-4">
            <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
              <User size={12} />
              <span className="truncate">{model.author || 'Unknown'}</span>
            </div>
            <h3 className="font-bold text-gray-900 truncate text-lg" title={model.name}>
              {model.name}
            </h3>
          </div>
          <div className="flex flex-col items-end gap-1">
            {isCurrent && (
              <span className="flex-shrink-0 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Active
              </span>
            )}
            {memoryInfo && (
              <span className={`flex-shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                memoryInfo.fits_in_vram 
                  ? 'bg-green-100 text-green-800' 
                  : availableVram > 0 ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-600'
              }`} title={`Estimated VRAM: ${memoryInfo.total_gb} GB (Rec: ${memoryInfo.recommended_vram_gb} GB)`}>
                {memoryInfo.fits_in_vram ? (
                  <><CheckCircle size={10} className="mr-1" /> Fits in VRAM</>
                ) : availableVram > 0 ? (
                  <><HardDrive size={10} className="mr-1" /> Partial Offload</>
                ) : (
                  <><HardDrive size={10} className="mr-1" /> {memoryInfo.total_gb} GB</>
                )}
              </span>
            )}
          </div>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-4 text-xs text-gray-500 mb-4">
          {model.downloads !== undefined && (
            <div className="flex items-center gap-1" title="Downloads">
              <Download size={14} />
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
              <span>{formatDate(model.last_modified)}</span>
            </div>
          )}
          {model.size_gb && (
            <div className="flex items-center gap-1" title="Size">
              <HardDrive size={14} />
              <span>{model.size_gb} GB</span>
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

        {/* Action Button */}
        <button
          onClick={handleAction}
          disabled={buttonDisabled}
          className={`w-full flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            onDownload
              ? 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 hover:text-primary-600 hover:border-primary-300'
              : isCurrent
              ? 'bg-green-100 text-green-700 cursor-default'
              : 'bg-primary-600 text-white hover:bg-primary-700 shadow-sm hover:shadow'
          }`}
        >
          {buttonLabel}
        </button>
      </div>
    </div>
  );
}
