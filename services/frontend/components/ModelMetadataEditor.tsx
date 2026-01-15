"use client";

import { useState, useEffect, useCallback } from "react";
import {
  X,
  Save,
  Link,
  User,
  FileText,
  Tag,
  Loader2,
  Search,
  ArrowRight,
  Check,
  ExternalLink,
  ChevronDown,
} from "lucide-react";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/utils";

interface ModelMetadataEditorProps {
  model: {
    model_id: string;
    name: string;
    author?: string;
    description?: string;
    repo_id?: string;
    huggingface_url?: string;
    tags?: string[];
    has_metadata?: boolean;
  };
  onClose: () => void;
  onSave: () => void;
}

interface HFSearchResult {
  id?: string;
  model_id?: string;
  author: string;
  downloads: number;
  likes: number;
  tags: string[];
  name?: string;
}

interface HFFile {
  rfilename?: string;
  filename?: string;
  size?: number;
  size_str?: string;
  size_info?: string;
}

type EditorMode = "search" | "manual";

export default function ModelMetadataEditor({
  model,
  onClose,
  onSave,
}: ModelMetadataEditorProps) {
  const [mode, setMode] = useState<EditorMode>("search");

  // Manual mode fields - initialize with defaults, will be updated if model exists
  const [name, setName] = useState(model?.name || "");
  const [author, setAuthor] = useState(model?.author || "");
  const [description, setDescription] = useState(model?.description || "");
  const [repoId, setRepoId] = useState(model?.repo_id || "");
  const [huggingfaceUrl, setHuggingfaceUrl] = useState(
    model?.huggingface_url || ""
  );
  const [tags, setTags] = useState(model?.tags?.join(", ") || "");

  // Search mode fields
  const [searchQuery, setSearchQuery] = useState(
    (model?.name || "")
      .replace(/[-_]/g, " ")
      .replace(/\.(gguf|bin)$/i, "")
      .slice(0, 50)
  );
  const [searchResults, setSearchResults] = useState<HFSearchResult[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<HFSearchResult | null>(null);
  const [repoFiles, setRepoFiles] = useState<HFFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);

  // Common state
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track mousedown to prevent closing when dragging text selection outside modal
  const [mouseDownInside, setMouseDownInside] = useState(false);

  // Update state when model changes
  useEffect(() => {
    if (model) {
      setName(model.name || "");
      setAuthor(model.author || "");
      setDescription(model.description || "");
      setRepoId(model.repo_id || "");
      setHuggingfaceUrl(model.huggingface_url || "");
      setTags(model.tags?.join(", ") || "");
      setSearchQuery(
        (model.name || "")
          .replace(/[-_]/g, " ")
          .replace(/\.(gguf|bin)$/i, "")
          .slice(0, 50)
      );
    }
  }, [model]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      // Only close on Escape if not typing in an input field
      if (
        e.key === "Escape" &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA"
      ) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  useEffect(() => {
    if (repoId && !huggingfaceUrl) {
      setHuggingfaceUrl(`https://huggingface.co/${repoId}`);
    }
  }, [repoId, huggingfaceUrl]);

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      setError("Please enter a search query");
      return;
    }

    setSearching(true);
    setError(null);
    setSearchResults([]);
    setSelectedRepo(null);
    setRepoFiles([]);
    setSelectedFile(null);

    try {
      // Search for models - append "gguf" if not already in query
      const query = searchQuery.trim();
      const searchQueryWithGGUF = query.toLowerCase().includes("gguf")
        ? query
        : `${query} gguf`;

      console.log("Searching with query:", searchQueryWithGGUF);
      const response: any = await api.searchModels(searchQueryWithGGUF, 20);
      console.log("Search response:", response);

      // Handle different response formats - backend returns array directly
      let results: HFSearchResult[] = [];
      if (Array.isArray(response)) {
        results = response;
      } else if (
        response &&
        typeof response === "object" &&
        "results" in response &&
        Array.isArray(response.results)
      ) {
        results = response.results;
      } else if (
        response &&
        typeof response === "object" &&
        "data" in response &&
        Array.isArray(response.data)
      ) {
        results = response.data;
      }

      console.log("Parsed results:", results);
      setSearchResults(results);

      if (results.length === 0) {
        setError(
          `No repositories found for "${query}". Try different search terms or check your spelling.`
        );
      } else {
        setError(null);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      console.error("Search error:", err);
      setError(`Search failed: ${message}. Please try again.`);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }, [searchQuery]);

  const handleSelectRepo = async (repo: HFSearchResult) => {
    setSelectedRepo(repo);
    setLoadingFiles(true);
    setRepoFiles([]);
    setSelectedFile(null);
    setError(null);

    try {
      const repoId = repo.id || repo.model_id;
      if (!repoId) {
        throw new Error("Repository ID is missing");
      }

      const data = await api.getModelFiles(repoId);

      // Backend returns files with 'filename' field, but we need to normalize to 'rfilename' for compatibility
      const allFiles = data.files || [];
      const ggufFiles = allFiles
        .map((f: any) => {
          // Normalize: use 'filename' if 'rfilename' is not present
          const filename = f.rfilename || f.filename || "";
          return {
            ...f,
            rfilename: filename, // Always set rfilename for consistency
            filename: filename, // Keep filename too
            size: f.size || 0, // Default size to 0 if not provided
          };
        })
        .filter(
          (f: HFFile) =>
            f.rfilename &&
            typeof f.rfilename === "string" &&
            f.rfilename.toLowerCase().endsWith(".gguf")
        );

      setRepoFiles(ggufFiles);

      const modelId = model.model_id || '';
      const currentName = modelId
        ? modelId.split(/[/\\]/).pop()?.toLowerCase() || ""
        : "";
      const match = ggufFiles.find((f: HFFile) => {
        const fname = (f.rfilename || f.filename || "").toLowerCase();
        return (
          fname === currentName ||
          fname.includes(currentName.replace(".gguf", "")) ||
          currentName.includes(fname.replace(".gguf", ""))
        );
      });

      if (match) {
        setSelectedFile(match.rfilename || match.filename || "");
      } else if (ggufFiles.length === 1) {
        setSelectedFile(ggufFiles[0].rfilename || ggufFiles[0].filename || "");
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      console.error("Error fetching files:", err);
      setError(`Failed to load files from repository: ${message}`);
    } finally {
      setLoadingFiles(false);
    }
  };

  const handleLinkAndOrganize = async () => {
    if (!selectedRepo) {
      setError("Please select a repository");
      return;
    }

    const repoId = selectedRepo.id || selectedRepo.model_id;
    if (!repoId) {
      setError("Repository ID is missing");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const modelId = model.model_id || '';
      if (!modelId) {
        setError("Model ID is missing");
        return;
      }
      await api.linkAndOrganizeModel(
        modelId,
        repoId,
        selectedFile || undefined
      );
      onSave();
      onClose();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      console.error("Error linking model:", err);
      setError(message || "Failed to link model");
    } finally {
      setSaving(false);
    }
  };

  const handleManualSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const metadata = {
        name: name.trim() || undefined,
        author: author.trim() || undefined,
        description: description.trim() || undefined,
        repo_id: repoId.trim() || undefined,
        huggingface_url: huggingfaceUrl.trim() || undefined,
        tags: tags.trim()
          ? tags
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean)
          : undefined,
      };

      const modelId = model.model_id || '';
      if (!modelId) {
        setError("Model ID is missing");
        return;
      }
      await api.setModelMetadata(modelId, metadata);
      onSave();
      onClose();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      console.error("Error saving metadata:", err);
      setError(message || "Failed to save metadata");
    } finally {
      setSaving(false);
    }
  };

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

  // Early return if model is null (after all hooks)
  if (!model) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onMouseDown={handleBackdropMouseDown}
      onMouseUp={handleBackdropMouseUp}
    >
      <div
        className="modal-content bg-white rounded shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col"
        onMouseDown={handleContentMouseDown}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-6 border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-900">
                Edit Model Metadata
              </h2>
              <p
                className="text-sm text-gray-500 mt-1 truncate max-w-md"
                title={model.model_id || 'Unknown'}
              >
                {model.model_id || 'Unknown'}
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded hover:bg-gray-100 transition-colors"
              title="Close (Esc)"
            >
              <X size={24} className="text-gray-500" />
            </button>
          </div>

          {/* Mode Tabs */}
          <div className="flex gap-2">
            <button
              onClick={() => setMode("search")}
              className={`flex-1 py-2 px-4 rounded font-medium transition-colors ${
                mode === "search"
                  ? "bg-primary-100 text-primary-700 border-2 border-primary-300"
                  : "bg-gray-100 text-gray-600 border-2 border-transparent hover:bg-gray-200"
              }`}
            >
              <Search size={16} className="inline mr-2" />
              Find on HuggingFace
            </button>
            <button
              onClick={() => setMode("manual")}
              className={`flex-1 py-2 px-4 rounded font-medium transition-colors ${
                mode === "manual"
                  ? "bg-primary-100 text-primary-700 border-2 border-primary-300"
                  : "bg-gray-100 text-gray-600 border-2 border-transparent hover:bg-gray-200"
              }`}
            >
              <FileText size={16} className="inline mr-2" />
              Manual Entry
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {mode === "search" ? (
            <div className="space-y-4">
              {/* Search Box */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Search HuggingFace for GGUF repositories
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                    placeholder="e.g., mistral 7b, llama 3, noromaid..."
                    className="flex-1 px-4 py-2.5 border border-gray-300 rounded focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-all"
                  />
                  <button
                    onClick={handleSearch}
                    disabled={searching || !searchQuery.trim()}
                    className="px-4 py-2.5 bg-primary-600 text-white rounded font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                  >
                    {searching ? (
                      <Loader2 size={18} className="animate-spin" />
                    ) : (
                      <Search size={18} />
                    )}
                    Search
                  </button>
                </div>
              </div>

              {/* Search Results */}
              {searchResults.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Select Repository ({searchResults.length} found)
                  </label>
                  <div className="border border-gray-200 rounded max-h-48 overflow-y-auto">
                    {searchResults.map((repo) => {
                      const repoId = repo.id || repo.model_id || "";
                      return (
                        <button
                          key={repoId}
                          onClick={() => handleSelectRepo(repo)}
                          className={`w-full text-left px-4 py-3 border-b border-gray-100 last:border-b-0 hover:bg-gray-50 transition-colors ${
                            (selectedRepo?.id || selectedRepo?.model_id) ===
                            repoId
                              ? "bg-primary-50 border-l-4 border-l-primary-500"
                              : ""
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-gray-900 truncate">
                                {repoId}
                              </div>
                              <div className="text-xs text-gray-500 flex gap-3 mt-1">
                                <span>
                                  Downloads:{" "}
                                  {repo.downloads?.toLocaleString() || 0}
                                </span>
                                <span>Likes: {repo.likes || 0}</span>
                              </div>
                            </div>
                            {(selectedRepo?.id || selectedRepo?.model_id) ===
                              repoId && (
                              <Check
                                size={20}
                                className="text-primary-600 flex-shrink-0"
                              />
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* File Selection */}
              {selectedRepo && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Select Quantization File (optional - keeps original if not
                    selected)
                  </label>
                  {loadingFiles ? (
                    <div className="flex items-center justify-center py-6 text-gray-500">
                      <Loader2 size={20} className="animate-spin mr-2" />
                      Loading files...
                    </div>
                  ) : repoFiles.length > 0 ? (
                    <div className="relative">
                      <select
                        value={selectedFile || ""}
                        onChange={(e) =>
                          setSelectedFile(e.target.value || null)
                        }
                        className="w-full px-4 py-2.5 border border-gray-300 rounded focus:ring-2 focus:ring-primary-500 focus:border-primary-500 appearance-none bg-white transition-all"
                      >
                        <option value="">Keep original filename</option>
                        {repoFiles.map((file) => {
                          const filename =
                            file.rfilename || file.filename || "";
                          const size = file.size || 0;
                          const sizeStr =
                            file.size_str ||
                            (size > 0 ? formatBytes(size) : "");
                          const quantInfo = file.size_info
                            ? ` - ${file.size_info}`
                            : "";
                          return (
                            <option key={filename} value={filename}>
                              {filename}
                              {sizeStr
                                ? ` (${sizeStr}${quantInfo})`
                                : quantInfo
                                ? ` (${quantInfo.trim()})`
                                : ""}
                            </option>
                          );
                        })}
                      </select>
                      <ChevronDown
                        size={18}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
                      />
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500 py-2">
                      No GGUF files found in this repository
                    </p>
                  )}
                </div>
              )}

              {/* Selected Summary */}
              {selectedRepo &&
                (() => {
                  const repoId = selectedRepo.id || selectedRepo.model_id || "";
                  const author =
                    selectedRepo.author || repoId.split("/")[0] || "Unknown";
                  const repoName =
                    repoId.split("/")[1] || repoId.split("/").pop() || "";
                  return (
                    <div className="bg-primary-50 border border-primary-200 rounded p-4">
                      <h4 className="font-medium text-primary-900 mb-2">
                        Ready to Link
                      </h4>
                      <div className="text-sm text-primary-700 space-y-1">
                        <p>
                          <strong>Repository:</strong> {repoId}
                        </p>
                        <p>
                          <strong>Your file:</strong> {model.model_id || 'Unknown'}
                        </p>
                        {selectedFile && (
                          <p>
                            <strong>Rename to:</strong> {selectedFile}
                          </p>
                        )}
                        <p className="text-primary-600 mt-2 flex items-center gap-1">
                          <ArrowRight size={14} />
                          Will move to: data/models/{author}/{repoName}/
                        </p>
                      </div>
                    </div>
                  );
                })()}
            </div>
          ) : (
            /* Manual Mode Form */
            <div className="space-y-5">
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                  <FileText size={16} />
                  Display Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g., Mistral 7B Instruct"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-all"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                  <User size={16} />
                  Author / Creator
                </label>
                <input
                  type="text"
                  value={author}
                  onChange={(e) => setAuthor(e.target.value)}
                  placeholder="e.g., TheBloke, Meta, Mistral AI"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-all"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                  <Link size={16} />
                  HuggingFace Repository ID
                </label>
                <input
                  type="text"
                  value={repoId}
                  onChange={(e) => setRepoId(e.target.value)}
                  placeholder="e.g., TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-all"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Format: author/model-name (auto-fills URL)
                </p>
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                  <ExternalLink size={16} />
                  HuggingFace URL
                </label>
                <input
                  type="url"
                  value={huggingfaceUrl}
                  onChange={(e) => setHuggingfaceUrl(e.target.value)}
                  placeholder="https://huggingface.co/..."
                  className="w-full px-4 py-2.5 border border-gray-300 rounded focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-all"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                  <FileText size={16} />
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief description of the model..."
                  rows={3}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-all resize-none"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                  <Tag size={16} />
                  Tags
                </label>
                <input
                  type="text"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="e.g., gguf, mistral, 7b, q4_k_m"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-all"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Separate tags with commas
                </p>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 bg-gray-50 rounded-b-2xl flex-shrink-0">
          <div className="flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2.5 bg-white border border-gray-300 rounded font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>

            {mode === "search" ? (
              <button
                onClick={handleLinkAndOrganize}
                disabled={saving || !selectedRepo}
                className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <Link size={18} />
                )}
                {saving ? "Linking..." : "Link & Organize"}
              </button>
            ) : (
              <button
                onClick={handleManualSave}
                disabled={saving}
                className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <Save size={18} />
                )}
                {saving ? "Saving..." : "Save Metadata"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
