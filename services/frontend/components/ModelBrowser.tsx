"use client";

import { useState, useEffect, useMemo } from "react";
import {
  X,
  Search,
  Filter,
  Library,
  Globe,
  FolderSearch,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useSettings } from "@/contexts/SettingsContext";
import { useToast } from "@/contexts/ToastContext";
import LoadModelDialog from "./LoadModelDialog";
import ModelSearchResultCard from "./ModelSearchResultCard";
import SystemStatus from "./SystemStatus";
import RepoDetailsModal from "./RepoDetailsModal";
import DownloadManager, { DownloadBadge } from "./DownloadManager";
import ModelMetadataEditor from "./ModelMetadataEditor";
import ResizableSidebar from "./ResizableSidebar";

interface LoadDialogModel {
  id: string;
  name: string;
  isMoe?: boolean;
  moeInfo?: any;
}

interface ModelBrowserProps {
  onClose: () => void;
}

type Tab = "discover" | "installed";

export default function ModelBrowser({ onClose }: ModelBrowserProps) {
  const [activeTab, setActiveTab] = useState<Tab>("discover");
  const [models, setModels] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [loadDialogModel, setLoadDialogModel] =
    useState<LoadDialogModel | null>(null);
  const [modelMetadata, setModelMetadata] = useState<Record<string, any>>({});
  const { currentModel, refresh: refreshSettings } = useSettings();
  const { showSuccess, showError, showInfo } = useToast();
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [showDownloadManager, setShowDownloadManager] = useState(false);
  const [editingModel, setEditingModel] = useState<any | null>(null);

  // Filters
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [minParams, setMinParams] = useState<number>(0);
  const [maxParams, setMaxParams] = useState<number>(70);
  const [quantFilter, setQuantFilter] = useState<string>("all");

  // Advanced Settings
  const [, setAvailableVram] = useState<number>(0);
  const [targetContext, setTargetContext] = useState<number>(4096);
  const [gpuLayers, setGpuLayers] = useState<number>(-1);
  const [useFlashAttn, setUseFlashAttn] = useState<boolean>(false);
  const [nBatch, setNBatch] = useState<number>(512);
  const [offloadKqv, setOffloadKqv] = useState<boolean>(true);

  useEffect(() => {
    loadModels();
    loadSystemInfo();
    loadModelMetadata();
    // Model status is now managed by SettingsContext (auto-refreshes every 30s)
    // No need for separate polling
  }, []);

  const loadModelMetadata = async () => {
    try {
      const result = (await api.getAllModelMetadata()) as any;
      if (result?.models) {
        const metadataMap: Record<string, any> = {};
        for (const model of result.models) {
          metadataMap[model.model_id] = model;
        }
        setModelMetadata(metadataMap);
      }
    } catch (error) {
      console.error("Error loading model metadata:", error);
    }
  };

  const handleScanLocal = async (forceRefresh: boolean = false) => {
    setScanning(true);
    try {
      const result = (await api.discoverModels(forceRefresh)) as any;
      console.log("Discovery result:", result);

      // Reload models and metadata
      await loadModels();
      await loadModelMetadata();

      const count = result?.models?.length || 0;
      showSuccess(`Discovered ${count} model(s)! Check the Installed tab.`);
    } catch (error) {
      console.error("Error scanning for models:", error);
      showError("Error scanning for models. Check the console for details.");
    } finally {
      setScanning(false);
    }
  };

  const loadSystemInfo = async () => {
    try {
      const info = (await api.getSystemInfo()) as any;
      if (info.gpu?.available && info.gpu.devices?.length > 0) {
        // Sum up VRAM from all GPUs
        const totalVram = info.gpu.devices.reduce(
          (acc: number, dev: any) => acc + dev.total_memory_gb,
          0
        );
        setAvailableVram(totalVram);
      }
    } catch (error) {
      console.error("Error loading system info:", error);
    }
  };

  const saveGlobalSettings = async () => {
    try {
      await api.updateSettings({
        default_load_options: {
          n_ctx: targetContext,
          n_gpu_layers: gpuLayers,
          use_flash_attention: useFlashAttn,
          n_batch: nBatch,
          offload_kqv: offloadKqv,
        },
      });
      showSuccess("Global loading settings saved!");
    } catch (error) {
      console.error("Error saving settings:", error);
      showError("Failed to save settings");
    }
  };

  // Initial search on mount
  useEffect(() => {
    if (activeTab === "discover" && searchResults.length === 0 && !loading) {
      handleSearch("GGUF"); // Default search to show something
    }
  }, [activeTab]);

  // Model status is now managed by SettingsContext
  // No need for separate loadCurrentModelStatus function

  const loadModels = async () => {
    try {
      const data = (await api.listModels()) as any;
      setModels(data);
    } catch (error) {
      console.error("Error loading models:", error);
    }
  };

  const handleSearch = async (query: string = searchQuery) => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const results = (await api.searchModels(query)) as any;
      setSearchResults(results);
    } catch (error) {
      console.error("Error searching models:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (repoId: string, filename?: string) => {
    if (!filename) {
      showInfo("Please select a specific file to download");
      return;
    }

    try {
      const result = (await api.downloadModel(repoId, filename)) as any;
      console.log("Download started:", result);

      // Open download manager to show progress
      setShowDownloadManager(true);
    } catch (error) {
      console.error("Error starting download:", error);
      showError("Error starting download: " + (error as Error).message);
    }
  };

  const handleDownloadComplete = async () => {
    // Refresh model list when a download completes
    await loadModels();
    await loadModelMetadata();
  };

  const handleDeleteModel = async (modelId: string) => {
    try {
      await api.deleteModel(modelId);
      // Refresh the list after deletion
      await loadModels();
      await loadModelMetadata();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      console.error("Failed to delete model:", err);
      throw new Error(message || "Failed to delete model");
    }
  };

  // Filter logic
  const filteredSearchResults = useMemo(() => {
    return searchResults.filter((model) => {
      // Extract parameters from model name/tags
      const extractParamsFromModel = (modelData: any): number | null => {
        const name = modelData.model_id?.toLowerCase() || "";
        const tags = modelData.tags || [];

        // Check tags first
        for (const tag of tags) {
          const match = tag.match(/(\d+)b/i);
          if (match) return parseInt(match[1]);
        }

        // Check name
        const nameMatch = name.match(/(\d+)b/i);
        if (nameMatch) return parseInt(nameMatch[1]);

        return null;
      };

      const params = extractParamsFromModel(model);

      // Filter by parameter range
      if (params !== null) {
        if (params < minParams || params > maxParams) return false;
      }

      return true;
    });
  }, [searchResults, minParams, maxParams]);

  const filteredInstalledModels = useMemo(() => {
    return models
      .filter((model) => {
        const name = model.name.toLowerCase();
        if (searchQuery && !name.includes(searchQuery.toLowerCase()))
          return false;
        return true;
      })
      .map((model) => {
        // Enhance with discovered metadata
        const metadata = modelMetadata[model.model_id];
        if (metadata) {
          return {
            ...model,
            repo_id: metadata.repo_id,
            repo_name: metadata.repo_name,
            author: metadata.author,
            architecture: metadata.architecture,
            parameters: metadata.parameters,
            quantization: metadata.quantization,
            context_length: metadata.context_length,
            moe: metadata.moe, // Include MoE info from metadata
            discovered: true,
          };
        }
        return model;
      });
  }, [models, searchQuery, modelMetadata]);

  return (
    <>
      {/* ModelBrowser Container - hidden when LoadModelDialog is open */}
      {!loadDialogModel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 sm:p-8">
          <div className="bg-white w-full max-w-6xl h-[85vh] rounded-2xl shadow-2xl flex overflow-hidden border border-gray-200">
            {/* Sidebar Filters */}
            <ResizableSidebar
              initialWidth={256}
              minWidth={180}
              maxWidth={500}
              side="right"
              className="bg-gray-50 border-r border-gray-200 p-6 flex flex-col gap-6 overflow-y-auto"
            >
              <div>
                <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2 mb-6">
                  <Filter size={20} /> Filters
                </h2>

                <div className="space-y-6">
                  <div>
                    <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3 block">
                      Model Size (Billions of Parameters)
                    </label>
                    <div className="space-y-4">
                      <div>
                        <label className="text-xs text-gray-600 block mb-1">
                          Min: {minParams}B
                        </label>
                        <input
                          type="range"
                          min="0"
                          max="70"
                          step="1"
                          value={minParams}
                          onChange={(e) => setMinParams(Number(e.target.value))}
                          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-600 block mb-1">
                          Max: {maxParams}B
                        </label>
                        <input
                          type="range"
                          min="0"
                          max="70"
                          step="1"
                          value={maxParams}
                          onChange={(e) => setMaxParams(Number(e.target.value))}
                          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
                        />
                      </div>
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3 block">
                      Quantization
                    </label>
                    <div className="space-y-2">
                      {["all", "q4", "q5", "q8", "f16"].map((q) => (
                        <label
                          key={q}
                          className="flex items-center gap-2 cursor-pointer group"
                        >
                          <input
                            type="radio"
                            name="quant"
                            checked={quantFilter === q}
                            onChange={() => setQuantFilter(q)}
                            className="w-4 h-4 text-primary-600 border-gray-300 focus:ring-primary-500"
                          />
                          <span className="text-sm text-gray-700 group-hover:text-gray-900 capitalize">
                            {q === "all" ? "Any" : q.toUpperCase()}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="pt-4 border-t border-gray-200">
                    <h3 className="text-sm font-bold text-gray-900 mb-3">
                      Loading Settings
                    </h3>

                    <div className="space-y-4">
                      <div>
                        <label className="text-xs text-gray-600 block mb-1">
                          Context Size
                        </label>
                        <select
                          value={targetContext}
                          onChange={(e) =>
                            setTargetContext(Number(e.target.value))
                          }
                          className="w-full text-sm border-gray-300 rounded-md shadow-sm focus:border-primary-500 focus:ring-primary-500"
                        >
                          <option value="2048">2048 (2k)</option>
                          <option value="4096">4096 (4k)</option>
                          <option value="8192">8192 (8k)</option>
                          <option value="16384">16384 (16k)</option>
                          <option value="32768">32768 (32k)</option>
                        </select>
                      </div>

                      <div>
                        <label className="text-xs text-gray-600 block mb-1">
                          GPU Layers
                        </label>
                        <input
                          type="number"
                          value={gpuLayers}
                          onChange={(e) => setGpuLayers(Number(e.target.value))}
                          className="w-full text-sm border-gray-300 rounded-md shadow-sm focus:border-primary-500 focus:ring-primary-500"
                          placeholder="-1 for all"
                        />
                        <p className="text-xs text-gray-400 mt-1">
                          -1 = Offload all to GPU
                        </p>
                      </div>

                      <div>
                        <label className="text-xs text-gray-600 block mb-1">
                          Chunk Size
                        </label>
                        <input
                          type="number"
                          value={nBatch}
                          onChange={(e) => setNBatch(Number(e.target.value))}
                          className="w-full text-sm border-gray-300 rounded-md shadow-sm focus:border-primary-500 focus:ring-primary-500"
                          placeholder="512"
                        />
                      </div>

                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={useFlashAttn}
                          onChange={(e) => setUseFlashAttn(e.target.checked)}
                          className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                        />
                        <span className="text-sm text-gray-700">
                          Flash Attention
                        </span>
                      </label>

                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={offloadKqv}
                          onChange={(e) => setOffloadKqv(e.target.checked)}
                          className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                        />
                        <span className="text-sm text-gray-700">
                          Offload KV Cache
                        </span>
                      </label>

                      <button
                        onClick={saveGlobalSettings}
                        className="w-full btn-secondary text-xs py-2"
                      >
                        Save as Defaults
                      </button>
                    </div>
                  </div>

                  {/* System Monitor */}
                  <div className="pt-4 border-t border-gray-200">
                    <SystemStatus />
                  </div>
                </div>
              </div>

              <div className="mt-auto">
                <div className="p-4 bg-primary-50 rounded-xl border border-primary-100">
                  <h3 className="text-sm font-semibold text-primary-900 mb-1">
                    Pro Tip
                  </h3>
                  <p className="text-xs text-primary-700">
                    Search for "GGUF" to find compatible models. Look for Q4_K_M
                    quantization for best balance.
                  </p>
                </div>

                {/* View Mode Toggle */}
                {activeTab === "discover" && (
                  <div className="flex bg-gray-100 p-1 rounded-lg">
                    <button
                      onClick={() => setViewMode("grid")}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                        viewMode === "grid"
                          ? "bg-white text-gray-900 shadow-sm"
                          : "text-gray-500 hover:text-gray-700"
                      }`}
                      title="Grid View"
                    >
                      <svg
                        className="w-4 h-4"
                        fill="currentColor"
                        viewBox="0 0 16 16"
                      >
                        <rect x="1" y="1" width="6" height="6" rx="1" />
                        <rect x="9" y="1" width="6" height="6" rx="1" />
                        <rect x="1" y="9" width="6" height="6" rx="1" />
                        <rect x="9" y="9" width="6" height="6" rx="1" />
                      </svg>
                    </button>
                    <button
                      onClick={() => setViewMode("list")}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                        viewMode === "list"
                          ? "bg-white text-gray-900 shadow-sm"
                          : "text-gray-500 hover:text-gray-700"
                      }`}
                      title="List View"
                    >
                      <svg
                        className="w-4 h-4"
                        fill="currentColor"
                        viewBox="0 0 16 16"
                      >
                        <rect x="1" y="2" width="14" height="2" rx="1" />
                        <rect x="1" y="7" width="14" height="2" rx="1" />
                        <rect x="1" y="12" width="14" height="2" rx="1" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
            </ResizableSidebar>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0">
              {/* Header */}
              <div className="h-20 border-b border-gray-200 flex items-center px-8 justify-between bg-white">
                <div className="flex items-center gap-8">
                  <div className="flex bg-gray-100 p-1 rounded-lg">
                    <button
                      onClick={() => setActiveTab("discover")}
                      className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                        activeTab === "discover"
                          ? "bg-white text-gray-900 shadow-sm"
                          : "text-gray-500 hover:text-gray-700"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Globe size={16} />
                        Discover
                      </div>
                    </button>
                    <button
                      onClick={() => setActiveTab("installed")}
                      className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                        activeTab === "installed"
                          ? "bg-white text-gray-900 shadow-sm"
                          : "text-gray-500 hover:text-gray-700"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Library size={16} />
                        Installed
                      </div>
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {/* Downloads Button */}
                  <DownloadBadge onClick={() => setShowDownloadManager(true)} />

                  {/* Scan Local Models Button */}
                  <button
                    onClick={() => handleScanLocal(false)}
                    disabled={scanning}
                    className="btn-secondary flex items-center gap-2 py-2 px-4"
                    title="Scan data/models folder for manually added GGUF files and find their HuggingFace sources"
                  >
                    {scanning ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <FolderSearch size={16} />
                    )}
                    {scanning ? "Scanning..." : "Scan Local"}
                  </button>

                  <button
                    onClick={onClose}
                    className="btn-icon text-gray-400 hover:text-gray-600 hover:bg-gray-100"
                  >
                    <X size={24} />
                  </button>
                </div>
              </div>

              {/* Search Bar Area */}
              <div className="p-8 pb-4">
                <div className="relative max-w-2xl mx-auto">
                  <Search
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400"
                    size={20}
                  />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) =>
                      e.key === "Enter" && handleSearch(searchQuery)
                    }
                    placeholder={
                      activeTab === "discover"
                        ? "Search HuggingFace models (e.g. 'llama 3 gguf')..."
                        : "Search installed models..."
                    }
                    className="w-full pl-12 pr-4 py-4 bg-gray-50 border border-gray-200 rounded-xl text-lg focus:ring-2 focus:ring-primary-500 focus:bg-white transition-all shadow-sm"
                  />
                  {activeTab === "discover" && (
                    <button
                      onClick={() => handleSearch(searchQuery)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 btn-primary py-2 px-4"
                      disabled={loading}
                    >
                      {loading ? "Searching..." : "Search"}
                    </button>
                  )}
                </div>
              </div>

              {/* Content Area */}
              <div className="flex-1 overflow-y-auto px-8 pb-8">
                {activeTab === "discover" ? (
                  <div
                    className={
                      viewMode === "grid"
                        ? "grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6"
                        : "space-y-3"
                    }
                  >
                    {filteredSearchResults.map((model) => (
                      <ModelSearchResultCard
                        key={model.model_id}
                        model={model}
                        onViewDetails={(id) => setSelectedModelId(id)}
                      />
                    ))}
                    {filteredSearchResults.length === 0 && !loading && (
                      <div className="col-span-full text-center py-20 text-gray-500">
                        <Search size={48} className="mx-auto mb-4 opacity-20" />
                        <p className="text-lg">
                          No models found. Try a different search term.
                        </p>
                      </div>
                    )}
                    {loading && (
                      <div className="col-span-full flex justify-center py-20">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
                    {filteredInstalledModels.map((model) => {
                      const isCurrentModel = Boolean(
                        currentModel &&
                          (currentModel.includes(model.model_id) ||
                            model.model_id ===
                              currentModel.split(/[/\\]/).pop())
                      );
                      return (
                        <ModelSearchResultCard
                          key={model.model_id}
                          model={model}
                          isCurrent={isCurrentModel}
                          onLoad={(modelId) => {
                            // Auto-detect MoE from model name if not set in metadata
                            const modelName = (
                              model.name || modelId
                            ).toUpperCase();
                            const isMoeFromName =
                              modelName.includes("MOE") ||
                              modelName.includes("MIXTURE");
                            const isMoe = model.moe?.is_moe || isMoeFromName;

                            setLoadDialogModel({
                              id: modelId,
                              name: model.name || modelId,
                              isMoe: isMoe,
                              moeInfo: model.moe,
                            });
                          }}
                          onEditMetadata={(m) => setEditingModel(m)}
                          onDelete={handleDeleteModel}
                        />
                      );
                    })}
                    {filteredInstalledModels.length === 0 && (
                      <div className="col-span-full text-center py-20 text-gray-500">
                        <Library
                          size={48}
                          className="mx-auto mb-4 opacity-20"
                        />
                        <p className="text-lg">No installed models found.</p>
                        <button
                          onClick={() => setActiveTab("discover")}
                          className="text-primary-600 hover:underline mt-2"
                        >
                          Go to Discover to download models
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Load Model Dialog - Rendered OUTSIDE ModelBrowser container with higher z-index */}
      {loadDialogModel && (
        <LoadModelDialog
          modelId={loadDialogModel.id}
          modelName={loadDialogModel.name}
          isMoe={loadDialogModel.isMoe}
          moeInfo={loadDialogModel.moeInfo}
          onClose={() => setLoadDialogModel(null)}
          onSuccess={() => {
            setLoadDialogModel(null);
            refreshSettings(); // Refresh settings to get updated model status
            loadModels();
          }}
        />
      )}

      {/* Repo Details Modal */}
      {selectedModelId && (
        <RepoDetailsModal
          modelId={selectedModelId}
          onClose={() => setSelectedModelId(null)}
          onDownload={(filename) => {
            handleDownload(selectedModelId, filename);
            setSelectedModelId(null);
          }}
        />
      )}

      {/* Download Manager */}
      <DownloadManager
        isOpen={showDownloadManager}
        onClose={() => setShowDownloadManager(false)}
        onDownloadComplete={handleDownloadComplete}
      />

      {/* Metadata Editor */}
      {editingModel && (
        <ModelMetadataEditor
          model={editingModel}
          onClose={() => setEditingModel(null)}
          onSave={() => {
            loadModels();
            loadModelMetadata();
          }}
        />
      )}
    </>
  );
}
