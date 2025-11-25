"use client";

import { useState, useEffect } from "react";
import { Volume2, CheckCircle, XCircle, Loader, Settings } from "lucide-react";
import { api } from "@/lib/api";
import { useServiceStatus } from "@/contexts/ServiceStatusContext";

export default function TTSSettings() {
  const { statuses } = useServiceStatus();
  const [backends, setBackends] = useState<any[]>([]);
  const [currentBackend, setCurrentBackend] = useState<any>(null);
  const [voices, setVoices] = useState<any[]>([]);
  const [options, setOptions] = useState<any>({});
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedBackend, setSelectedBackend] = useState<string>("");
  const [updating, setUpdating] = useState(false);
  const [chatterboxServiceStatus, setChatterboxServiceStatus] =
    useState<any>(null);
  const [chatterboxInstalling, setChatterboxInstalling] = useState(false);
  const [chatterboxStarting, setChatterboxStarting] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  // Poll logs when installing or starting
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (chatterboxInstalling || chatterboxStarting) {
      interval = setInterval(async () => {
        try {
          const result = await api.getChatterboxServiceLogs();
          if (result && result.logs) {
            setLogs(result.logs);
          }
        } catch (error) {
          console.error("Error fetching logs:", error);
        }
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [chatterboxInstalling, chatterboxStarting]);

  // Poll status when installing or starting to keep state in sync
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (chatterboxInstalling || chatterboxStarting || chatterboxServiceStatus?.is_installing) {
      interval = setInterval(async () => {
        await loadChatterboxServiceStatus();
      }, 2000); // Poll every 2 seconds
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [chatterboxInstalling, chatterboxStarting, chatterboxServiceStatus?.is_installing]);

  useEffect(() => {
    loadTTSInfo();
    loadChatterboxServiceStatus();
  }, []);

  // Get backend health from global context
  const backendHealth: Record<string, any> = {
    piper: statuses?.tts?.piper || { status: 'offline' },
    chatterbox: statuses?.tts?.chatterbox || { status: 'offline' },
    kokoro: statuses?.tts?.kokoro || { status: 'offline' },
  };

  const loadChatterboxServiceStatus = async () => {
    try {
      const status = await api.getChatterboxServiceStatus() as any;
      setChatterboxServiceStatus(status);
      
      // Sync local state with backend state
      if (status.is_installing) {
        setChatterboxInstalling(true);
      } else if (chatterboxInstalling && !status.is_installing) {
        setChatterboxInstalling(false);
      }
    } catch (error) {
      console.error("Error loading Chatterbox service status:", error);
    }
  };

  const handleInstallChatterbox = async () => {
    try {
      setChatterboxInstalling(true);
      await api.installChatterboxService();
      // Installation started in background, polling will track progress
    } catch (error: any) {
      console.error("Error installing Chatterbox:", error);
      alert(`Failed to install: ${error.message || "Unknown error"}`);
      setChatterboxInstalling(false);
    }
  };

  const handleStartChatterbox = async () => {
    try {
      setChatterboxStarting(true);
      const result = await api.startChatterboxService() as any;
      alert(result.message || "Service started");
      await loadChatterboxServiceStatus();
      await loadTTSInfo(); // Reload to update backend status
    } catch (error: any) {
      console.error("Error starting Chatterbox:", error);
      alert(`Failed to start: ${error.message || "Unknown error"}`);
    } finally {
      setChatterboxStarting(false);
    }
  };

  const handleStopChatterbox = async () => {
    try {
      const result = await api.stopChatterboxService() as any;
      alert(result.message || "Service stopped");
      await loadChatterboxServiceStatus();
      await loadTTSInfo();
    } catch (error: any) {
      console.error("Error stopping Chatterbox:", error);
      alert(`Failed to stop: ${error.message || "Unknown error"}`);
    }
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
      if (current) {
        setCurrentBackend(current);
        setSelectedBackend(current.name || settingsData.current_backend);
        await loadBackendDetails(current.name || settingsData.current_backend);
      }
    } catch (error) {
      console.error("Error loading TTS info:", error);
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

      // Load models if available (Coqui)
      if (backendName === "coqui") {
        try {
          const modelsData = await api.getTTSModels(backendName) as any;
          setModels(modelsData.models || []);
        } catch (e) {
          console.error("Error loading models:", e);
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
        loadChatterboxServiceStatus();
      }
    } catch (error) {
      console.error("Error switching backend:", error);
      // Revert on failure
      setSelectedBackend(previousBackend);
      alert("Failed to switch TTS backend. Check console for details.");
      // Reload to ensure consistent state
      loadTTSInfo();
    } finally {
      setUpdating(false);
    }
  };

  const handleUpdateOptions = async () => {
    if (!selectedBackend) return;
    try {
      setUpdating(true);
      // Convert structured options to flat format for API
      const flatOptions: any = {};
      if (options.voice) flatOptions.voice = options.voice;

      // Handle structured options (with value key)
      Object.keys(options).forEach((key) => {
        if (key === "voice") return;
        const value = options[key];
        if (typeof value === "object" && value !== null && "value" in value) {
          flatOptions[key] = value.value;
        } else {
          flatOptions[key] = value;
        }
      });

      // Save options without blocking UI - fire and forget for instant feedback
      api.setTTSBackendOptions(selectedBackend, flatOptions).catch((error) => {
        console.error("Error updating options:", error);
        // Only show error if it's critical
        if (
          error.message?.includes("not found") ||
          error.message?.includes("failed")
        ) {
          alert("Failed to update TTS options");
        }
      });

      // Update local state immediately for instant feedback
      setUpdating(false);
    } catch (error) {
      console.error("Error updating options:", error);
      setUpdating(false);
    }
  };

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
      return newOptions;
    });
  };

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
        {/* Chatterbox Service Management */}
        {selectedBackend === "chatterbox" && chatterboxServiceStatus && (
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">
                  Chatterbox TTS API Service
                </span>
                <span
                  className={`text-xs px-2 py-1 rounded ${
                    chatterboxServiceStatus.is_running
                      ? "bg-green-100 text-green-700"
                      : chatterboxServiceStatus.installed
                      ? "bg-yellow-100 text-yellow-700"
                      : "bg-red-100 text-red-700"
                  }`}
                >
                  {chatterboxServiceStatus.is_running
                    ? "Running"
                    : chatterboxServiceStatus.installed
                    ? "Installed"
                    : "Not Installed"}
                </span>
              </div>
            </div>

            {!chatterboxServiceStatus.installed && (
              <div className="mb-2">
                <button
                  onClick={handleInstallChatterbox}
                  disabled={chatterboxInstalling}
                  className="btn-primary w-full text-sm"
                >
                  {chatterboxInstalling
                    ? "Installing..."
                    : "Install Chatterbox TTS API"}
                </button>
                <p className="text-xs text-gray-600 mt-1">
                  This will clone and set up the Chatterbox TTS API server
                </p>
              </div>
            )}

            {chatterboxServiceStatus.installed &&
              !chatterboxServiceStatus.is_running && (
                <div className="mb-2">
                  <button
                    onClick={handleStartChatterbox}
                    disabled={chatterboxStarting}
                    className="btn-primary w-full text-sm"
                  >
                    {chatterboxStarting ? "Starting..." : "Start Service"}
                  </button>
                </div>
              )}

            {chatterboxServiceStatus.is_running && (
              <div className="space-y-2">
                <div className="text-xs text-gray-600">
                  <div>API: {chatterboxServiceStatus.api_url}</div>
                  {chatterboxServiceStatus.frontend_url && (
                    <div>Frontend: {chatterboxServiceStatus.frontend_url}</div>
                  )}
                </div>
                <button
                  onClick={handleStopChatterbox}
                  className="btn-secondary w-full text-sm"
                >
                  Stop Service
                </button>
              </div>
            )}

            {chatterboxServiceStatus.error_message && (
              <p className="text-xs text-red-600 mt-2">
                {chatterboxServiceStatus.error_message}
              </p>
            )}

            {/* Log Viewer */}
            {(chatterboxInstalling || chatterboxStarting || logs.length > 0) && (
              <div className="mt-3 bg-black text-green-400 p-3 rounded text-xs font-mono h-48 overflow-y-auto">
                <div className="flex justify-between items-center mb-2 border-b border-gray-700 pb-1">
                  <span>Installation/Startup Logs</span>
                  <button 
                    onClick={() => setLogs([])}
                    className="text-gray-500 hover:text-gray-300"
                  >
                    Clear
                  </button>
                </div>
                <div className="flex flex-col-reverse">
                  {logs.slice().reverse().map((log, i) => (
                    <div key={i} className="whitespace-pre-wrap break-all">
                      {log}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Backend Selection */}
        <div>
          <label className="block text-sm font-medium mb-2">TTS Backend</label>
          <div className="space-y-2">
            {backends.map((backend: any) => {
              const health = backendHealth[backend.name];
              const isAccessible = health?.accessible;
              const isService = health?.is_service;
              const needsService = ['piper', 'chatterbox', 'kokoro'].includes(backend.name);
              
              return (
                <div
                  key={backend.name}
                  className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                    backend.is_current
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                  onClick={() => !updating && handleSwitchBackend(backend.name)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 flex-wrap">
                      {getStatusIcon(backend.status, backend.is_generating)}
                      <span className="font-medium capitalize">
                        {backend.name}
                      </span>
                      {backend.is_current && (
                        <span className="text-xs bg-blue-500 text-white px-2 py-0.5 rounded">
                          Current
                        </span>
                      )}
                      
                      {/* Service Health Indicator */}
                      {needsService && (
                        isAccessible === true ? (
                          <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded flex items-center gap-1">
                            <CheckCircle size={12} />
                            Service Running
                          </span>
                        ) : isAccessible === false ? (
                          <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded flex items-center gap-1">
                            <XCircle size={12} />
                            Service Offline
                          </span>
                        ) : (
                          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded flex items-center gap-1">
                            <Loader size={12} className="animate-spin" />
                            Checking...
                          </span>
                        )
                      )}
                      
                      {/* OpenAI external API indicator */}
                      {backend.name === 'openai' && health?.is_external && (
                        isAccessible === true ? (
                          <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded flex items-center gap-1">
                            <CheckCircle size={12} />
                            API Connected {health.authenticated && '🔑'}
                          </span>
                        ) : health?.needs_configuration ? (
                          <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded flex items-center gap-1">
                            <Settings size={12} />
                            Not Configured
                          </span>
                        ) : isAccessible === false ? (
                          <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded flex items-center gap-1">
                            <XCircle size={12} />
                            API Offline
                          </span>
                        ) : (
                          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded flex items-center gap-1">
                            <Loader size={12} className="animate-spin" />
                            Testing API...
                          </span>
                        )
                      )}
                      
                      {/* Local backend indicator */}
                      {!needsService && isService === false && !health?.is_external && (
                        <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                          Local
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-gray-500">
                      {backend.status === "ready" && !backend.is_generating
                        ? "Ready"
                        : backend.is_generating
                        ? "Generating..."
                        : backend.status}
                    </div>
                  </div>
                  
                  {/* Warning if service is offline but backend is current */}
                  {needsService && backend.is_current && isAccessible === false && (
                    <p className="text-xs text-orange-600 mt-2 flex items-center gap-1">
                      ⚠️ Service is not running. TTS generation will fail. Start the {backend.name} service to use this backend.
                    </p>
                  )}
                  
                  {/* Service error details */}
                  {health?.error && !backend.error_message && (
                    <p className="text-xs text-gray-500 mt-1">
                      {health.error}
                    </p>
                  )}
                  
                  {backend.error_message && (
                    <p className="text-xs text-red-500 mt-1">
                      {backend.error_message}
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
            {voices.length > 0 && (
              <div>
                <label className="block text-sm font-medium mb-1">Voice</label>
                <select
                  value={getOptionValue("voice") || ""}
                  onChange={(e) => updateOptionValue("voice", e.target.value)}
                  className="input w-full"
                >
                  <option value="">Default</option>
                  {voices.map((voice: any) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.name} {voice.language ? `(${voice.language})` : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Backend-specific Options */}
            {currentBackend.name === "chatterbox" && (
              <div className="space-y-3 p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Settings size={16} />
                  <span className="text-sm font-medium">
                    Chatterbox Options
                  </span>
                </div>
                
                {/* Voice Upload Section */}
                <div className="border-b border-gray-200 pb-3 mb-3">
                  <label className="block text-sm font-medium mb-2">Upload Custom Voice</label>
                  <div className="flex flex-col gap-2">
                    <input
                      type="file"
                      accept=".wav,.mp3,.ogg,.flac"
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        
                        try {
                          setUpdating(true);
                          const name = file.name.replace(/\.[^/.]+$/, "");
                          await api.uploadVoice(file, name);
                          alert(`Voice '${name}' uploaded successfully!`);
                          // Reload voices
                          await loadBackendDetails("chatterbox");
                        } catch (error: any) {
                          console.error("Error uploading voice:", error);
                          alert(`Upload failed: ${error.message}`);
                        } finally {
                          setUpdating(false);
                          // Reset input
                          e.target.value = "";
                        }
                      }}
                      className="text-sm w-full"
                    />
                    <p className="text-xs text-gray-500">
                      Upload a short audio sample (wav/mp3). It will be converted to 48kHz mono for Chatterbox.
                    </p>
                  </div>
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
                    <input
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
                      className="input w-full"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Random seed for reproducible generation (leave empty for
                      random)
                    </p>
                  </div>
                )}
              </div>
            )}

            {currentBackend.name === "kokoro" && (
              <div className="space-y-3 p-3 bg-gray-50 rounded-lg">
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
                  </div>
                )}
                {options.temperature && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Temperature:{" "}
                      {getOptionValue("temperature")?.toFixed(2) || "0.70"}
                    </label>
                    <input
                      type="range"
                      min={options.temperature?.min || 0.0}
                      max={options.temperature?.max || 1.0}
                      step={options.temperature?.step || 0.1}
                      value={getOptionValue("temperature") || 0.7}
                      onChange={(e) =>
                        updateOptionValue(
                          "temperature",
                          parseFloat(e.target.value)
                        )
                      }
                      className="w-full"
                    />
                  </div>
                )}
                {options.top_p && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Top P: {getOptionValue("top_p")?.toFixed(2) || "0.90"}
                    </label>
                    <input
                      type="range"
                      min={options.top_p?.min || 0.0}
                      max={options.top_p?.max || 1.0}
                      step={options.top_p?.step || 0.05}
                      value={getOptionValue("top_p") || 0.9}
                      onChange={(e) =>
                        updateOptionValue("top_p", parseFloat(e.target.value))
                      }
                      className="w-full"
                    />
                  </div>
                )}
                {options.top_k && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Top K: {getOptionValue("top_k") || "50"}
                    </label>
                    <input
                      type="range"
                      min={options.top_k?.min || 1}
                      max={options.top_k?.max || 100}
                      step={options.top_k?.step || 1}
                      value={getOptionValue("top_k") || 50}
                      onChange={(e) =>
                        updateOptionValue("top_k", parseInt(e.target.value))
                      }
                      className="w-full"
                    />
                  </div>
                )}
              </div>
            )}

            {currentBackend.name === "coqui" && (
              <div className="space-y-3 p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-2 mb-2">
                  <Settings size={16} />
                  <span className="text-sm font-medium">Coqui Options</span>
                </div>
                {options.model_name && (
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      Model
                    </label>
                    <select
                      value={
                        getOptionValue("model_name") ||
                        options.model_name?.value ||
                        ""
                      }
                      onChange={(e) =>
                        updateOptionValue("model_name", e.target.value)
                      }
                      className="input w-full"
                    >
                      {models.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))}
                    </select>
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

            {currentBackend.name === "pyttsx3" && (
              <div className="space-y-3 p-3 bg-gray-50 rounded-lg">
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

            <button
              onClick={handleUpdateOptions}
              disabled={updating}
              className="btn-primary w-full mt-4"
            >
              {updating ? "Updating..." : "Update TTS Options"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
