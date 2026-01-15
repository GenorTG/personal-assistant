'use client';

import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ModelSearchBarProps {
  searchQuery: string;
  onSearchQueryChange: (query: string) => void;
  onSearch: () => void;
  loading: boolean;
  activeTab: 'discover' | 'installed';
}

export function ModelSearchBar({
  searchQuery,
  onSearchQueryChange,
  onSearch,
  loading,
  activeTab,
}: ModelSearchBarProps) {
  return (
    <div className="w-full px-4 sm:px-8 pb-4 border-b border-border bg-background">
      <div className="relative w-full max-w-2xl mx-auto">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" size={20} />
        <Input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && activeTab === 'discover' && onSearch()}
          placeholder={
            activeTab === 'discover'
              ? "Search HuggingFace models (e.g. 'llama 3 gguf') or use size filters..."
              : 'Search installed models...'
          }
          className="w-full pl-12 pr-4 sm:pr-24 py-4 text-base sm:text-lg"
        />
        <div className={cn("hidden", activeTab === 'discover' && "block absolute right-3 top-1/2 -translate-y-1/2")}>
          <Button onClick={onSearch} disabled={loading} size="sm">
            {loading ? 'Searching...' : 'Search'}
          </Button>
        </div>
      </div>
    </div>
  );
}




