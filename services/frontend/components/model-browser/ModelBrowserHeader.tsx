'use client';

import { Globe, Library, X, FolderSearch, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DownloadBadge } from '@/components/DownloadManager';

type Tab = 'discover' | 'installed';

interface ModelBrowserHeaderProps {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  onClose: () => void;
  onScanLocal: () => void;
  scanning: boolean;
  onShowDownloadManager: () => void;
}

export function ModelBrowserHeader({
  activeTab,
  onTabChange,
  onClose,
  onScanLocal,
  scanning,
  onShowDownloadManager,
}: ModelBrowserHeaderProps) {
  return (
    <div className="h-20 border-b border-border flex items-center px-4 sm:px-8 justify-between bg-background flex-shrink-0">
      <div className="flex items-center gap-4 sm:gap-8">
        <Tabs value={activeTab} onValueChange={(v) => onTabChange(v as Tab)}>
          <TabsList>
            <TabsTrigger value="discover" className="flex items-center gap-2">
              <Globe size={16} />
              <span className="hidden sm:inline">Discover</span>
            </TabsTrigger>
            <TabsTrigger value="installed" className="flex items-center gap-2">
              <Library size={16} />
              <span className="hidden sm:inline">Installed</span>
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <div className="flex items-center gap-2">
        <DownloadBadge onClick={onShowDownloadManager} />
        <Button
          onClick={onScanLocal}
          disabled={scanning}
          variant="outline"
          size="sm"
          className="flex items-center gap-2"
          title="Scan data/models folder for manually added GGUF files and find their HuggingFace sources"
        >
          {scanning ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <FolderSearch size={16} />
          )}
          <span className="hidden sm:inline">{scanning ? 'Scanning...' : 'Scan Local'}</span>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground"
        >
          <X size={24} />
        </Button>
      </div>
    </div>
  );
}




