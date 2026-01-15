"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Volume2, CheckCircle, XCircle, Loader, Settings } from "lucide-react";
import { api } from "@/lib/api";
import { useServiceStatus } from "@/contexts/ServiceStatusContext";
import { useToast } from "@/contexts/ToastContext";
import VoiceCloningPanel from "./VoiceCloningPanel";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export default function TTSSettings() {
  const { statuses } = useServiceStatus();
  const { showError, showSuccess } = useToast();
  const [backends, setBackends] = useState<any[]>([]);
  const [currentBackend, setCurrentBackend] = useState<any>(null);
  const [voices, setVoices] = useState<any[]>([]);
  const [options, setOptions] = useState<any>({});
  const [models] = useState<string[]>([]);
  const [availableModels, setAvailableModels] = useState<any[]>([]);
  const [currentModel, setCurrentModel] = useState<string>("");
  const [, setCustomVoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedBackend, setSelectedBackend] = useState<string>("");
  const [updating, setUpdating] = useState(false);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastSavedOptionsRef = useRef<string>("");

  useEffect(() => {
    loadTTSInfo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Get backend health from global context - use only ServiceStatusContext
  const getBackendStatus = (backendName: string): 'ready' | 'offline' | 'error' => {
    const status = statuses?.tts?.[backendName as keyof typeof statuses.tts];
    return status?.status || 'offline';
  };

  const loadTTSInfo = async () => {
    try {
      setLoading(true);
      const settingsData = await api.getTTSSettings() as any;
      const backendsData = settingsData.available_backends || [];
      setBackends(backendsData);

      // Find current backend
      const current =
        settingsData.current_backend_info ||
        backendsData.find((b: any) => b.is_current);
      if (current && current.name) {
        setCurrentBackend(current);
        setSelectedBackend(current.name || settingsData.current_backend);
        await loadBackendDetails(current.name || settingsData.current_backend);
      } else if (settingsData.current_backend) {
        // Try to load details for the current backend even if info is missing
        setSelectedBackend(settingsData.current_backend);
        await loadBackendDetails(settingsData.current_backend);
      }
    } catch (error) {
      console.error("Error loading TTS info:", error);
      // Set default backends if error occurs
      setBackends([
        { name: "piper", status: "error", is_current: false },
        { name: "kokoro", status: "error", is_current: false },
        { name: "chatterbox", status: "error", is_current: false }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const loadBackendDetails = async (backendName: string) => {
    try {
      const info = await api.getTTSBackendInfo(backendName) as any;
      setOptions(info.options || {});

      const voicesData = await api.getTTSVoices(backendName) as any;
      setVoices(voicesData.voices || []);

      // Load models if available (Piper, Coqui)
      if (backendName === "piper" || backendName === "coqui") {
        try {
          const modelsData = await api.getTTSModels(backendName) as any;
          const modelsList = modelsData.models || [];
          setAvailableModels(modelsList);
          
          // Get current model from status
          if (backendName === "piper") {
            try {
              const status = await api.getTTSBackendInfo(backendName) as any;
              if (status.model_status) {
                const modelPath = status.model_status.model_path;
                if (modelPath) {
                  const modelName = modelPath.split('/').pop()?.replace('.onnx', '') || '';
                  setCurrentModel(modelName);
                }
              }
            } catch (e) {
              console.error("Error getting current model:", e);
            }
          }
        } catch (e) {
          console.error("Error loading models:", e);
        }
      }

      // Load custom voices for Chatterbox
      if (backendName === "chatterbox") {
        try {
          const customVoicesData = await api.getCustomVoices(backendName) as any;
          setCustomVoices(customVoicesData.voices || []);
        } catch (e) {
          console.error("Error loading custom voices:", e);
        }
      }
    } catch (error) {
      console.error("Error loading backend details:", error);
    }
  };

  const handleSwitchBackend = async (backendName: string) => {
    // Optimistic update - switch immediately
    const previousBackend = selectedBackend;
    setSelectedBackend(backendName);
    
    // Reset options while loading new backend
    setOptions({});
    setVoices([]);
    
    try {
      setUpdating(true);

      // Call API to switch
      await api.switchTTSBackend(backendName);

      // Reload info to get updated status and options
      await loadTTSInfo();
      
      // If it's chatterbox, check status too
      if (backendName === "chatterbox") {
        // loadChatterboxServiceStatus(); // Removed: relying on global status
      }
    } catch (error) {
      console.error("Error switching backend:", error);
      // Revert on failure
      setSelectedBackend(previousBackend);
      showError("Failed to switch TTS backend. Check console for details.");
      // Reload to ensure consistent state
      loadTTSInfo();
    } finally {
      setUpdating(false);
    }
  };

  const saveOptions = useCallback(async (optionsToSave: any) => {
    if (!selectedBackend) return;
    
    // Convert structured options to flat format for API
    const flatOptions: any = {};
    if (optionsToSave.voice) flatOptions.voice = optionsToSave.voice;

    // Handle structured options (with value key)
    Object.keys(optionsToSave).forEach((key) => {
      if (key === "voice") return;
      const value = optionsToSave[key];
      if (typeof value === "object" && value !== null && "value" in value) {
        flatOptions[key] = value.value;
      } else {
        flatOptions[key] = value;
      }
    });

    // Check if options actually changed
    const optionsStr = JSON.stringify(flatOptions);
    if (optionsStr === lastSavedOptionsRef.current) {
      return; // No change, skip save
    }

    try {
      setUpdating(true);
      await api.setTTSBackendOptions(selectedBackend, flatOptions);
      lastSavedOptionsRef.current = optionsStr;
    } catch (error) {
      console.error("Error updating options:", error);
      // Only show error if it's critical
      if (
        error instanceof Error && (
          error.message?.includes("not found") ||
          error.message?.includes("failed")
        )
      ) {
        console.error("Failed to update TTS options:", error);
      }
    } finally {
      setUpdating(false);
    }
  }, [selectedBackend]);

  const updateOptionValue = (key: string, value: any) => {
    setOptions((prev: any) => {
      const newOptions = { ...prev };
      if (
        newOptions[key] &&
        typeof newOptions[key] === "object" &&
        "value" in newOptions[key]
      ) {
        newOptions[key] = { ...newOptions[key], value };
      } else {
        newOptions[key] = value;
      }
      
      // Auto-save with debouncing (500ms delay)
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      saveTimeoutRef.current = setTimeout(() => {
        saveOptions(newOptions);
      }, 500);
      
      return newOptions;
    });
  };
  
  // Save options when backend changes
  useEffect(() => {
    if (selectedBackend && Object.keys(options).length > 0) {
      // Reset last saved when backend changes
      lastSavedOptionsRef.current = "";
      // Auto-save current options for new backend
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      saveTimeoutRef.current = setTimeout(() => {
        saveOptions(options);
      }, 500);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBackend, saveOptions]);
  
  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  const getOptionValue = (key: string): any => {
    const opt = options[key];
    if (typeof opt === "object" && opt !== null && "value" in opt) {
      return opt.value;
    }
    return opt;
  };

  const getStatusIcon = (status: string, isGenerating: boolean) => {
    if (isGenerating) {
      return <Loader size={16} className="animate-spin text-blue-500" />;
    }
    if (status === "ready") {
      return <CheckCircle size={16} className="text-green-500" />;
    }
    return <XCircle size={16} className="text-red-500" />;
  };

  if (loading) {
    return (
      <div>
        <h3 className="font-semibold mb-4 flex items-center gap-2">
          <Volume2 size={20} />
          Text-to-Speech Settings
        </h3>
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  return (
    <div>
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        <Volume2 size={20} />
        Text-to-Speech Settings
      </h3>
      <div className="space-y-4">


        {/* Backend Selection */}
        <div>
          <label className="block text-sm font-medium mb-2">TTS Backend</label>
          <div className="space-y-2">
            {backends.map((backend: any) => {
              // Use ServiceStatusContext as source of truth
              const serviceStatus = getBackendStatus(backend.name);
              const isServiceReady = serviceStatus === 'ready';
              
              // For service-based backends, use service status; otherwise use backend status
              const needsService = ['piper', 'chatterbox', 'kokoro'].includes(backend.name);
              const effectiveStatus = needsService ? (isServiceReady ? "ready" : "error") : backend.status;
              const effectiveError = needsService && !isServiceReady ? `Service ${serviceStatus}` : backend.error_message;
              
              return (
                <div
                  key={backend.name}
                  className={`p-3 border rounded cursor-pointer transition-colors ${
                    backend.is_current
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                  onClick={() => !updating && handleSwitchBackend(backend.name)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 flex-wrap">
                      {getStatusIcon(effectiveStatus, backend.is_generating)}
                      <span className="font-medium capitalize">
                        {backend.name}
                      </span>
                      {backend.is_current && (
                        <span className="text-xs bg-blue-500 text-white px-2 py-0.5 rounded">
                          Current
                        </span>
                      )}
                      
                      {/* Service Status Indicator - only show for service-based backends */}
                      {needsService && (
                        <Badge 
                          variant={isServiceReady ? 'default' : 'destructive'}
                          className="text-xs flex items-center gap-1"
                        >
                          {isServiceReady ? (
                            <>
                              <CheckCircle size={12} />
                              Service Ready
                            </>
                          ) : (
                            <>
                              <XCircle size={12} />
                              Service Offline
                            </>
                          )}
                        </Badge>
                      )}
                    </div>
                    <div className="text-xs text-gray-500">
                      {effectiveStatus === "ready" && !backend.is_generating
                        ? "Ready"
                        : backend.is_generating
                        ? "Generating..."
                        : effectiveStatus}
                    </div>
                  </div>
                  
                  {/* Warning if service is offline but backend is current */}
                  {needsService && backend.is_current && !isServiceReady && (
                    <p className="text-xs text-orange-600 mt-2 flex items-center gap-1">
                      ⚠️ Service is not running. TTS generation will fail. Start the {backend.name} service to use this backend.
                    </p>
                  )}
                  
                  {/* Error message */}
                  {effectiveError && (
                    <p className="text-xs text-red-500 mt-1">
                      {effectiveError}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Current Backend Options */}
        {currentBackend && currentBackend.status === "ready" && (
          <>
            {/* Voice Selection */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm font-medium">Voice</label>
                <button
                  onClick={async () => {
                    try {
                      setUpdating(true);
                      await api.refreshTTSVoices(selectedBackend);
                      await loadBackendDetails(selectedBackend);
                      showSuccess("Voices refreshed successfully!");
                    } catch (error: any) {
                      console.error("Error refreshing voices:", error);
                      showError(`Failed to refresh voices: ${error.message}`);
                    } finally {
                      setUpdating(false);
                    }
                  }}
                  disabled={updating}
                  className="text-xs px-2 py-1 bg-blue-500 hover:bg-blue-600 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Refresh voices list (hot-reload)"
                >
                  {updating ? "Refreshing..." : "🔄 Refresh"}
                </button>
              </div>
              <div className={cn("hidden", voices.length > 0 && "block")}>
                <Select
                  value={getOptionValue("voice") || "default"}
                  onValueChange={(value) => updateOptionValue("voice", value === "default" ? "" : value)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Default" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">Default</SelectItem>
                    {voices.map((voice: any) => {
                      if (!voice) return null;
                      const voiceId = voice.id || 'unknown';
                      const voiceName = voice.name || voice.id || 'Unknown';
                      const language = voice.language || '';
                      return (
                        <SelectItem key={voiceId} value={voiceId}>
                          {voiceName} {language ? `(${language})` : ""}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
              </div>
              <div className={cn("hidden text-sm text-muted-foreground py-2", voices.length === 0 && "block")}>
                No voices available. Click "Refresh" to reload voices.
              </div>
            </div>

            {/* Backend-specific Options */}
            {currentBackend?.name === "chatterbox" && (
              <div className="space-y-3 p-3 bg-gray-50 rounded">
                <div className="flex items-center gap-2 mb-2">
                  <Settings size={16} />
                  <span className="text-sm font-medium">
                    Chatterbox Options
                  </span>
                </div>
                
                {/* Voice Cloning Section */}
                <div className="border-b border-gray-200 pb-3 mb-3">
                  <VoiceCloningPanel
                    backendName="chatterbox"
                    onVoiceUploaded={async () => {
                      await loadBackendDetails("chatterbox");
                    }}
                  />
                </div>

                {options.speed && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Speed: {getOptionValue("speed")?.toFixed(1) || "1.0"}
                    </label>
                    <input
                      type="range"
                      min={options.speed?.min || 0.5}
                      max={options.speed?.max || 2.0}
                      step={options.speed?.step || 0.1}
                      value={getOptionValue("speed") || 1.0}
                      onChange={(e) =>
                        updateOptionValue("speed", parseFloat(e.target.value))
                      }
                      className="w-full"
                    />
                  </div>
                )}
                {options.cfg_weight !== undefined && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      CFG Weight:{" "}
                      {getOptionValue("cfg_weight")?.toFixed(2) || "0.50"}
                    </label>
                    <input
                      type="range"
                      min={options.cfg_weight?.min || 0.0}
                      max={options.cfg_weight?.max || 2.0}
                      step={options.cfg_weight?.step || 0.05}
                      value={getOptionValue("cfg_weight") ?? 0.5}
                      onChange={(e) =>
                        updateOptionValue(
                          "cfg_weight",
                          parseFloat(e.target.value)
                        )
                      }
                      className="w-full"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Pace control (0.0-2.0)
                    </p>
                  </div>
                )}
                {options.temperature !== undefined && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Temperature:{" "}
                      {getOptionValue("temperature")?.toFixed(2) || "0.80"}
                    </label>
                    <input
                      type="range"
                      min={options.temperature?.min || 0.05}
                      max={options.temperature?.max || 5.0}
                      step={options.temperature?.step || 0.05}
                      value={getOptionValue("temperature") ?? 0.8}
                      onChange={(e) =>
                        updateOptionValue(
                          "temperature",
                          parseFloat(e.target.value)
                        )
                      }
                      className="w-full"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Sampling temperature
                    </p>
                  </div>
                )}
                {options.exaggeration !== undefined && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Exaggeration:{" "}
                      {getOptionValue("exaggeration")?.toFixed(2) || "0.50"}
                    </label>
                    <input
                      type="range"
                      min={options.exaggeration?.min || 0.25}
                      max={options.exaggeration?.max || 2.0}
                      step={options.exaggeration?.step || 0.05}
                      value={getOptionValue("exaggeration") ?? 0.5}
                      onChange={(e) =>
                        updateOptionValue(
                          "exaggeration",
                          parseFloat(e.target.value)
                        )
                      }
                      className="w-full"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Emotion intensity (0.25-2.0)
                    </p>
                  </div>
                )}
                {options.seed !== undefined && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Seed
                    </label>
                    <Input
                      type="number"
                      min={options.seed?.min ?? undefined}
                      max={options.seed?.max ?? undefined}
                      value={getOptionValue("seed") ?? ""}
                      onChange={(e) => {
                        const val = e.target.value;
                        updateOptionValue(
                          "seed",
                          val === "" ? null : parseInt(val)
                        );
                      }}
                      placeholder="Random (leave empty)"
                      className="w-full"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Random seed for reproducible generation (leave empty for
                      random)
                    </p>
                  </div>
                )}
              </div>
            )}

            {currentBackend?.name === "piper" && (
              <div className="space-y-3 p-3 bg-gray-50 rounded">
                <div className="flex items-center gap-2 mb-2">
                  <Settings size={16} />
                  <span className="text-sm font-medium">Piper Options</span>
                </div>
                
                {/* Model Selection */}
                {availableModels.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium mb-1">Voice Model</label>
                    <Select
                      value={currentModel || undefined}
                      onValueChange={async (modelId) => {
                        if (!modelId) return;
                        
                        try {
                          setUpdating(true);
                          await api.switchTTSModel("piper", modelId);
                          setCurrentModel(modelId);
                          showSuccess(`Switched to model: ${modelId}`);
                          await loadBackendDetails("piper");
                        } catch (error: any) {
                          console.error("Error switching model:", error);
                          showError(`Failed to switch model: ${error.message}`);
                        } finally {
                          setUpdating(false);
                        }
                      }}
                      disabled={updating}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Select model..." />
                      </SelectTrigger>
                      <SelectContent>
                        {availableModels.map((model: any) => {
                          if (!model) return null;
                          const modelId = model.id || model.name || 'unknown';
                          const modelName = model.name || model.id || 'Unknown';
                          const language = model.language || '';
                          return (
                            <SelectItem key={modelId} value={modelId}>
                              {modelName} {language ? `(${language})` : ""}
                            </SelectItem>
                          );
                        })}
                      </SelectContent>
                    </Select>
                    {currentModel && (
                      <p className="text-xs text-gray-500 mt-1">
                        Current: {currentModel}
                      </p>
                    )}
                  </div>
                )}
                
                {options.speed && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Speed: {getOptionValue("speed")?.toFixed(1) || "1.0"}
                    </label>
                    <input
                      type="range"
                      min={options.speed?.min || 0.5}
                      max={options.speed?.max || 2.0}
                      step={options.speed?.step || 0.1}
                      value={getOptionValue("speed") || 1.0}
                      onChange={(e) =>
                        updateOptionValue("speed", parseFloat(e.target.value))
                      }
                      className="w-full"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Speech speed multiplier (0.5-2.0)
                    </p>
                  </div>
                )}
              </div>
            )}

            {currentBackend?.name === "kokoro" && (
              <div className="space-y-3 p-3 bg-gray-50 rounded">
                <div className="flex items-center gap-2 mb-2">
                  <Settings size={16} />
                  <span className="text-sm font-medium">Kokoro Options</span>
                </div>
                {options.speed && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Speed: {getOptionValue("speed")?.toFixed(1) || "1.0"}
                    </label>
                    <input
                      type="range"
                      min={options.speed?.min || 0.5}
                      max={options.speed?.max || 2.0}
                      step={options.speed?.step || 0.1}
                      value={getOptionValue("speed") || 1.0}
                      onChange={(e) =>
                        updateOptionValue("speed", parseFloat(e.target.value))
                      }
                      className="w-full"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Speech speed multiplier (0.5-2.0)
                    </p>
                  </div>
                )}
                {options.lang && (
                  <div>
                    <label className="block text-sm font-medium mb-1">Language</label>
                    <Select
                      value={getOptionValue("lang") || "en-us"}
                      onValueChange={(value) => updateOptionValue("lang", value)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="en-us">English (US)</SelectItem>
                        <SelectItem value="en-gb">English (GB)</SelectItem>
                        <SelectItem value="es">Spanish</SelectItem>
                        <SelectItem value="fr">French</SelectItem>
                        <SelectItem value="de">German</SelectItem>
                        <SelectItem value="it">Italian</SelectItem>
                        <SelectItem value="pt">Portuguese</SelectItem>
                        <SelectItem value="ru">Russian</SelectItem>
                        <SelectItem value="ja">Japanese</SelectItem>
                        <SelectItem value="zh">Chinese</SelectItem>
                        <SelectItem value="ko">Korean</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-gray-500 mt-1">
                      Language code for synthesis
                    </p>
                  </div>
                )}
              </div>
            )}

            {currentBackend?.name === "coqui" && (
              <div className="space-y-3 p-3 bg-gray-50 rounded">
                <div className="flex items-center gap-2 mb-2">
                  <Settings size={16} />
                  <span className="text-sm font-medium">Coqui Options</span>
                </div>
                {options.model_name && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Model
                    </label>
                    <Select
                      value={
                        getOptionValue("model_name") ||
                        options.model_name?.value ||
                        ""
                      }
                      onValueChange={(value) =>
                        updateOptionValue("model_name", value)
                      }
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {models.map((model) => (
                          <SelectItem key={model} value={model}>
                            {model}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-gray-500 mt-1">
                      Changing model requires reinitialization
                    </p>
                  </div>
                )}
                {options.gpu && (
                  <div>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={getOptionValue("gpu") || false}
                        onChange={(e) =>
                          updateOptionValue("gpu", e.target.checked)
                        }
                        className="rounded"
                      />
                      <span className="text-sm font-medium">
                        Use GPU Acceleration
                      </span>
                    </label>
                  </div>
                )}
              </div>
            )}

            {currentBackend?.name === "pyttsx3" && (
              <div className="space-y-3 p-3 bg-gray-50 rounded">
                <div className="flex items-center gap-2 mb-2">
                  <Settings size={16} />
                  <span className="text-sm font-medium">
                    System TTS Options
                  </span>
                </div>
                {options.rate && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Rate: {getOptionValue("rate") || "150"} WPM
                    </label>
                    <input
                      type="range"
                      min={options.rate?.min || 50}
                      max={options.rate?.max || 300}
                      step={options.rate?.step || 10}
                      value={getOptionValue("rate") || 150}
                      onChange={(e) =>
                        updateOptionValue("rate", parseInt(e.target.value))
                      }
                      className="w-full"
                    />
                  </div>
                )}
                {options.volume && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Volume: {getOptionValue("volume")?.toFixed(1) || "0.9"}
                    </label>
                    <input
                      type="range"
                      min={options.volume?.min || 0.0}
                      max={options.volume?.max || 1.0}
                      step={options.volume?.step || 0.1}
                      value={getOptionValue("volume") || 0.9}
                      onChange={(e) =>
                        updateOptionValue("volume", parseFloat(e.target.value))
                      }
                      className="w-full"
                    />
                  </div>
                )}
              </div>
            )}

            {updating && (
              <div className="text-sm text-gray-500 mt-4 text-center">
                Saving...
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
